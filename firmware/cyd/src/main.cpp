#include <Arduino.h>
#include <SPI.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <esp_system.h>
#include <math.h>
#include "scanner_protocol.h"
#if __has_include("stoneinventory_config.h")
#include "stoneinventory_config.h"
#endif
#ifndef INVENTORY_WIFI_SSID
#define INVENTORY_WIFI_SSID ""
#endif
#ifndef INVENTORY_WIFI_PASSWORD
#define INVENTORY_WIFI_PASSWORD ""
#endif
#ifndef INVENTORY_API_BASE
#define INVENTORY_API_BASE ""
#endif
#ifndef INVENTORY_DEVICE_ID
#define INVENTORY_DEVICE_ID "kitchen-cyd-01"
#endif
#ifndef INVENTORY_SCANNER_NAME
#define INVENTORY_SCANNER_NAME "Netum Bluetooth"
#endif
#ifndef INVENTORY_SCANNER_MAC
#define INVENTORY_SCANNER_MAC ""
#endif
#ifndef INVENTORY_SCANNER_PIN
#define INVENTORY_SCANNER_PIN ""
#endif
#ifndef SCANNER_TEST_ONLY
#define SCANNER_TEST_ONLY 0
#endif
#if !DIAGNOSTICS_ONLY
#include <BluetoothSerial.h>
BluetoothSerial scanner;
QueueHandle_t rxBytes, netJobs, netReplies;
volatile bool rxOverflow=false, btReady=false, btAuthFailed=false;
struct NetJob { char path[64],body[640]; bool read; };
struct NetReply { int code; bool parsed,read; char json[2048]; };
bool netBusy=false, suspended=false, storageFault=false;
BarcodeFramer framer;
#endif

TFT_eSPI lcd;
SPIClass touchSpi(VSPI);
XPT2046_Touchscreen touch(33,36);
Preferences prefs;
const uint16_t BG=0x1082, FG=TFT_WHITE, GREEN=0x2B68;
enum Screen { HOME, SCAN_READY, BARCODE, EDIT_COUNT, CONFIRM, WAITING, RESULT, SCANNER_TEST, PAUSED };
Screen screen=HOME;
String action,input,barcode,itemName,resultText,lastTest,scanWarning;
int oldCount=0;
unsigned long resultAt=0,lastWifi=0,lastFrameByte=0;
unsigned int testCount=0,rejected=0;
float transform[6];
bool calibrated=false,resultSuccess=false;
struct Button { int x,y,w,h; String title; int id; };
Button buttons[16];int buttonCount=0;
void title(String a,String b="") {
  lcd.fillScreen(BG);lcd.setTextColor(FG,BG);
  lcd.drawString(a.substring(0,26),10,8,2);
  lcd.drawString(b.substring(0,44),10,32,1);buttonCount=0;
}
void button(int x,int y,int w,int h,String text,int id,uint16_t color=GREEN) {
  lcd.fillRoundRect(x,y,w,h,5,color);lcd.setTextColor(FG,color);
  lcd.drawCentreString(text,x+w/2,y+(h-16)/2,2);
  if(buttonCount<16)buttons[buttonCount++]={x,y,w,h,text,id};
}
void draw();
void status(String text,bool success=false) {
  resultText=text;resultSuccess=success;screen=RESULT;resultAt=millis();draw();
}
void waitRelease() { while(touch.touched())delay(20);delay(70); }
bool calibrate() {
  // Three non-collinear samples define a full affine transform (including axis swaps).
  const int px[3]={22,298,22}, py[3]={22,22,218};
  float rx[3],ry[3];
  for(int i=0;i<3;i++) {
    title("Touch calibration","Tap the small cross. Use a stylus or fingernail.");
    lcd.drawLine(px[i]-9,py[i],px[i]+9,py[i],TFT_YELLOW);
    lcd.drawLine(px[i],py[i]-9,px[i],py[i]+9,TFT_YELLOW);
    while(!touch.touched()) delay(10);
    long x=0,y=0; int n=0;
    for(int j=0;j<15;j++) { if(touch.touched()) { auto p=touch.getPoint(); x+=p.x;y+=p.y;n++; } delay(5); }
    if(!n) { i--; continue; }
    rx[i]=float(x)/n; ry[i]=float(y)/n; waitRelease();
  }
  float det=(rx[1]-rx[0])*(ry[2]-ry[0])-(rx[2]-rx[0])*(ry[1]-ry[0]);
  if(fabs(det)<1000) return false;
  transform[0]=276*(ry[2]-ry[0])/det;
  transform[1]=-276*(rx[2]-rx[0])/det;
  transform[2]=22-transform[0]*rx[0]-transform[1]*ry[0];
  transform[3]=-196*(ry[1]-ry[0])/det;
  transform[4]=196*(rx[1]-rx[0])/det;
  transform[5]=22-transform[3]*rx[0]-transform[4]*ry[0];
  calibrated=prefs.putBytes("touch",transform,sizeof(transform))==sizeof(transform);
  return calibrated;
}
String uuid() {
  uint8_t b[16]; esp_fill_random(b,16); b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;
  char out[37];
  snprintf(out,sizeof(out),"%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
    b[0],b[1],b[2],b[3],b[4],b[5],b[6],b[7],b[8],b[9],b[10],b[11],b[12],b[13],b[14],b[15]);
  return out;
}
bool request(String path,String body,JsonDocument &reply,int &code) {
  if(WiFi.status()!=WL_CONNECTED) { code=-1; return false; }
  WiFiClient client; HTTPClient http;
  http.setConnectTimeout(3000);http.setTimeout(12000);http.useHTTP10(true);
  if(!http.begin(client,String(INVENTORY_API_BASE)+path)) { code=-1;return false; }
  http.addHeader("Content-Type","application/json");
  code=body.length()?http.POST(body):http.GET();
  if(code<=0) { http.end();return false; }
  // Stream only fields needed by the terminal: do not allocate the full source product payload.
  StaticJsonDocument<512> filter;
  filter["status"]=true;filter["detail"]=true;filter["request_id"]=true;
  filter["name"]=true;filter["quantity"]=true;filter["package_size"]=true;
  filter["product"]["name"]=true;filter["product"]["package_size"]=true;
  filter["inventory"]["before"]=true;filter["inventory"]["after"]=true;
  auto error=deserializeJson(reply,http.getStream(),DeserializationOption::Filter(filter));
  http.end(); return !error;
}

#if !DIAGNOSTICS_ONLY
bool storeOutbox(const std::vector<ScanRequest> &records) {
  if(records.empty()) return !prefs.isKey("pending") || prefs.remove("pending");
  DynamicJsonDocument saved(8192);
  JsonArray items=saved.to<JsonArray>();
  for(const auto &r:records) {
    JsonObject row=items.createNestedObject();
    row["path"]=r.path.c_str();row["body"]=r.body.c_str();
  }
  if(saved.overflowed())return false;
  String json;serializeJson(saved,json);
  return prefs.putString("pending",json)==json.length();
}
PersistentOutbox outbox(storeOutbox);
bool restoreOutbox() {
  String raw=prefs.getString("pending","");
  if(!raw.length())return true;
  DynamicJsonDocument saved(8192);
  if(deserializeJson(saved,raw))return false;
  std::vector<ScanRequest> records;
  auto add=[&](JsonVariant row) {
    String path=row["path"]|"",body=row["body"]|"";
    StaticJsonDocument<640> decoded;
    if(deserializeJson(decoded,body))return false;
    String id=decoded["request_id"]|"";
    if(id.length()!=36 || body.length()>=640 || path.length()>=64)return false;
    records.push_back({path.c_str(),body.c_str(),id.c_str()});return true;
  };
  if(saved.is<JsonArray>()) { for(JsonVariant row:saved.as<JsonArray>())if(!add(row))return false; }
  else if(!add(saved.as<JsonVariant>()))return false; // migration of previous single pending request
  if(!outbox.restore(records))return false;
  if(!outbox.empty()) {
    StaticJsonDocument<640> body;deserializeJson(body,outbox.front().body.c_str());
    action=body["action"]|"edit";
  }
  return true;
}
void networkTask(void*) {
  NetJob job;
  for(;;)if(xQueueReceive(netJobs,&job,portMAX_DELAY)==pdTRUE) {
    NetReply answer{};answer.read=job.read;
    DynamicJsonDocument reply(2048);
    answer.parsed=request(job.path,job.body,reply,answer.code);
    size_t written=serializeJson(reply,answer.json,sizeof(answer.json));
    answer.json[sizeof(answer.json)-1]=0;
    if(written>=sizeof(answer.json)-1)answer.parsed=false;
    xQueueSend(netReplies,&answer,portMAX_DELAY);
  }
}
void bluetoothTask(void*) {
  scanner.onData([](const uint8_t *data,size_t length) {
    for(size_t i=0;i<length;i++)if(xQueueSend(rxBytes,data+i,0)!=pdTRUE)rxOverflow=true;
  });
  scanner.onAuthComplete([](bool success){btAuthFailed=!success;});
  btReady=scanner.begin("StoneInventory-CYD",true);
  if(strlen(INVENTORY_SCANNER_PIN))scanner.setPin(INVENTORY_SCANNER_PIN);
  if(!btReady) { vTaskDelete(nullptr);return; }
  Serial.println("Bluetooth SPP started; searching for configured scanner.");
  for(;;) {
    if(!scanner.connected(0)) {
      Serial.println("Connecting scanner (SPP mode required).");
      if(strlen(INVENTORY_SCANNER_MAC)) {
        uint8_t mac[6];int used=0;
        if(sscanf(INVENTORY_SCANNER_MAC,"%hhx:%hhx:%hhx:%hhx:%hhx:%hhx%n",
           &mac[0],&mac[1],&mac[2],&mac[3],&mac[4],&mac[5],&used)==6 &&
           used==int(strlen(INVENTORY_SCANNER_MAC)))scanner.connect(mac);
      } else scanner.connect(String(INVENTORY_SCANNER_NAME));
    }
    vTaskDelay(pdMS_TO_TICKS(10000));
  }
}
void dispatch() {
  if(netBusy || suspended || storageFault || outbox.empty())return;
  if(WiFi.status()!=WL_CONNECTED){suspended=true;screen=WAITING;draw();return;}
  NetJob job{};strlcpy(job.path,outbox.front().path.c_str(),sizeof(job.path));
  strlcpy(job.body,outbox.front().body.c_str(),sizeof(job.body));
  if(xQueueSend(netJobs,&job,0)==pdTRUE)netBusy=true;
}
void queueOperation(int quantity) {
  if(storageFault || suspended || outbox.size()>=PersistentOutbox::capacity) {
    rejected++;scanWarning="Not accepted: "+barcode;draw();return;
  }
  StaticJsonDocument<640> body;
  body["barcode"]=barcode;body["quantity"]=quantity;body["device_id"]=INVENTORY_DEVICE_ID;
  String id=uuid();body["request_id"]=id;
  String path="/api/scan";
  if(action=="edit"){path="/api/inventory/reconcile";body["expected_quantity"]=oldCount;}
  else body["action"]=action;
  String json;serializeJson(body,json);
  if(body.overflowed() || json.length()>=640 || !outbox.append({path.c_str(),json.c_str(),id.c_str()})) {
    rejected++;scanWarning="Not saved: "+barcode;screen=PAUSED;draw();return;
  }
  screen=SCAN_READY;input="";draw();dispatch();
}
void retry() {
  if(storageFault)return;
  suspended=false;screen=SCAN_READY;draw();dispatch();
}
void receiveReplies() {
  NetReply answer;
  if(xQueueReceive(netReplies,&answer,0)!=pdTRUE)return;
  netBusy=false;
  DynamicJsonDocument reply(2048);deserializeJson(reply,answer.json);
  if(answer.read) {
    if(answer.parsed && answer.code==200 && reply["quantity"].is<int>()) {
      oldCount=reply["quantity"].as<int>();itemName=reply["name"]|"Unidentified product";
      input="";screen=EDIT_COUNT;draw();
    } else status("Could not read product.\nCheck Wi-Fi / server.");
    return;
  }
  if(outbox.empty()) {storageFault=true;screen=WAITING;draw();return;}
  bool success=answer.parsed && answer.code==200 && reply["status"]=="success" &&
    reply["inventory"]["after"].is<int>() && reply["request_id"].as<String>()==outbox.front().id.c_str();
  bool definitiveError=answer.parsed && answer.code>=400 && answer.code<500;
  if(success || definitiveError) {
    if(!outbox.acknowledge(outbox.front().id)) {suspended=true;screen=WAITING;draw();return;}
    if(success) {
      String name=reply["product"]["name"]|"Unidentified product";
      resultText=name.substring(0,28)+"\n"+String(reply["inventory"]["before"].as<int>())+
        " -> "+String(reply["inventory"]["after"].as<int>())+"\nSaved on server";
      resultSuccess=true;resultAt=millis();screen=RESULT;draw();
      if(!rejected)dispatch();
    } else {
      suspended=true;resultSuccess=false;
      resultText=reply["detail"]|"Request rejected. Check inventory.";
      screen=WAITING;draw();
    }
  } else {suspended=true;screen=WAITING;draw();}
}
void submitBarcode() {
  if(input.length()<8 || input.length()>14)return;
  barcode=input;
  if(action!="edit"){queueOperation(1);return;}
  if(netBusy || !outbox.empty())return;
  NetJob job{};job.read=true;
  strlcpy(job.path,("/api/products/"+barcode).c_str(),sizeof(job.path));
  if(xQueueSend(netJobs,&job,0)==pdTRUE) {netBusy=true;title("Reading current count","Please wait. Inventory stays on the server.");}
}
void rejectScan(String reason) {
  if(screen==SCANNER_TEST || SCANNER_TEST_ONLY) {scanWarning=reason;draw();return;}
  rejected++;scanWarning=reason;
  if(!netBusy && outbox.empty())screen=PAUSED;
  draw();
}
void scannerInput() {
  if(rxOverflow) {
    rxOverflow=false;xQueueReset(rxBytes);framer.reset();
    rejectScan("Data overflow. Rescan rejected items.");return;
  }
  uint8_t byte;
  while(xQueueReceive(rxBytes,&byte,0)==pdTRUE) {
    std::string framed;auto result=framer.feed(byte,framed);lastFrameByte=millis();
    if(result==FrameResult::None)continue;
    if(result==FrameResult::Invalid){rejectScan("Invalid barcode. Digits + Enter only.");continue;}
    String code=framed.c_str();
    Serial.println("Barcode received: "+code);
    if(screen==SCANNER_TEST) {lastTest=code;testCount++;scanWarning="";draw();continue;}
    bool accepting=(screen==SCAN_READY || (screen==RESULT && resultSuccess)) &&
      (action=="add" || action=="remove" || action=="edit") && !suspended && !storageFault && !rejected;
    if(!accepting){rejectScan("Not accepted: "+code);continue;}
    if(WiFi.status()!=WL_CONNECTED){rejectScan("Wi-Fi offline. Rescan: "+code);continue;}
    barcode=code;
    if(action=="edit") {
      if(netBusy || !outbox.empty()){rejectScan("Finish current edit, then rescan.");continue;}
      input=code;submitBarcode();
    } else queueOperation(1);
  }
  // Never concatenate a partial frame across a disconnect or a long pause.
  if(lastFrameByte && millis()-lastFrameByte>2000 && framer.hasPartial()) {
    framer.reset();rejectScan("Incomplete barcode. Set Enter suffix.");
  }
}
#endif

void keypad() {
  lcd.setTextColor(TFT_YELLOW,BG);lcd.drawString(input.length()?input:"_",12,52,2);
  for(int i=0;i<9;i++)button(10+(i%3)*65,80+(i/3)*38,60,33,String(i+1),i+1);
  button(10,194,60,33,"DEL",10);button(75,194,60,33,"0",0);button(140,194,60,33,"CLR",11);
  button(210,80,100,65,screen==BARCODE?"ENTER":"REVIEW",12);
  button(210,160,100,65,"CANCEL",13,0x8200);
}
void draw() {
#if !DIAGNOSTICS_ONLY
  String bt=scanner.connected(0)?"BT connected":btAuthFailed?"BT pairing failed":"BT searching";
  if(screen==HOME) {
    title("STONEINVENTORY",WiFi.status()==WL_CONNECTED?"Wi-Fi connected":"Wi-Fi not connected");
    lcd.drawString(bt,10,50,2);
    button(10,75,145,55,"ADD",20);button(165,75,145,55,"REMOVE",21,0x8200);
    button(10,145,200,60,"EDIT COUNT",22);button(220,145,90,60,"BT TEST",26);
    button(250,210,60,25,"CAL",23);
  } else if(screen==SCANNER_TEST) {
    title("SCANNER TEST (no changes)",bt);
    lcd.drawString("Scans received: "+String(testCount),10,70,2);
    lcd.drawString(lastTest.length()?lastTest:"Scan a product barcode",10,105,2);
    lcd.drawString(scanWarning.substring(0,42),10,135,1);
    if(!SCANNER_TEST_ONLY)button(10,180,300,45,"HOME",13);
  } else if(screen==SCAN_READY) {
    title(action=="edit"?"EDIT: scan a product":action=="add"?"ADD: ready for next barcode":"REMOVE: ready for next barcode",bt);
    lcd.drawString("Saved requests: "+String(outbox.size())+" / 8",10,70,2);
    lcd.drawString(netBusy?"Sending to server...":"Scan the next item",10,100,2);
    lcd.drawString(scanWarning.substring(0,44),10,133,1);
    if(outbox.empty() && !netBusy) {
      button(10,175,145,50,"MANUAL",27);button(165,175,145,50,"EXIT MODE",13,0x8200);
    }
  } else if(screen==BARCODE || screen==EDIT_COUNT) {
    title(screen==BARCODE?"Enter barcode: "+action:"Actual package count",screen==EDIT_COUNT?"Current: "+String(oldCount)+" | "+itemName:"Include all leading zeros");keypad();
  } else if(screen==CONFIRM) {
    title("Confirm correction",itemName);
    lcd.drawCentreString(String(oldCount)+" -> "+input,160,80,4);
    lcd.drawCentreString("Correction, not consumption",160,120,2);
    button(10,170,145,55,"CANCEL",13,0x8200);button(165,170,145,55,"CONFIRM",24);
  } else if(screen==WAITING || screen==PAUSED) {
    title(storageFault?"Saved requests need attention":"SCANNING PAUSED",bt);
    lcd.drawString("Saved requests: "+String(outbox.size()),10,65,2);
    lcd.drawString((scanWarning.length()?scanWarning:resultText).substring(0,42),10,95,1);
    lcd.drawString(storageFault?"Do not erase flash. Check serial log.":"Retry saved items; rescan rejected ones.",10,120,1);
    if(!storageFault)button(10,170,300,55,outbox.empty()?"RESUME SCANNING":"RETRY SAFELY",25);
  } else {
    title("Inventory response",bt);lcd.setCursor(10,60);lcd.setTextFont(2);lcd.println(resultText);
    lcd.drawString("Queued: "+String(outbox.size()),10,140,2);
    if(rejected)lcd.drawString("Not accepted: "+String(rejected)+" (rescan)",10,165,2);
    if(outbox.empty() && !netBusy)button(10,190,300,40,"EXIT MODE",13);
  }
#endif
}
void tap(int id) {
#if !DIAGNOSTICS_ONLY
  if(id==25) {rejected=0;scanWarning="";retry();return;}
  if(id==13) {
    if(netBusy || !outbox.empty())return;
    screen=HOME;action="";input="";rejected=0;scanWarning="";framer.reset();draw();return;
  }
  if(id>=20 && id<=22){action=id==20?"add":id==21?"remove":"edit";input="";screen=SCAN_READY;draw();return;}
  if(id==26){screen=SCANNER_TEST;scanWarning="";framer.reset();draw();return;}
  if(id==27){screen=BARCODE;input="";draw();return;}
  if(id==23){do{calibrated=calibrate();}while(!calibrated);framer.reset();draw();return;}
  if(id==24){queueOperation(input.toInt());return;}
  if(screen!=BARCODE && screen!=EDIT_COUNT)return;
  if(id==12) {
    if(screen==BARCODE)submitBarcode();
    else if(input.length() && input.toInt()<=1000000){screen=CONFIRM;draw();}
    return;
  }
  if(id==10)input.remove(input.length()?input.length()-1:0);
  else if(id==11)input="";
  else if(id>=0 && id<=9 && input.length()<(screen==BARCODE?14:7))input+=String(id);
  draw();
#endif
}
void setup() {
  Serial.begin(115200);delay(300);
  lcd.init();lcd.setRotation(1);digitalWrite(21,HIGH);
  touchSpi.begin(25,39,32,33);touch.begin(touchSpi);touch.setRotation(1);
#if DIAGNOSTICS_ONLY
  lcd.fillScreen(TFT_RED);delay(600);lcd.fillScreen(TFT_GREEN);delay(600);lcd.fillScreen(TFT_BLUE);delay(600);
  title("DISPLAY OK - touch the screen","Diagnostics only. No network or inventory requests.");
#else
  if(!prefs.begin("stoneinventory",false)){title("Storage unavailable","Do not scan inventory yet.");while(true)delay(1000);}
  calibrated=prefs.getBytesLength("touch")==sizeof(transform);
  if(calibrated)prefs.getBytes("touch",transform,sizeof(transform));
  rxBytes=xQueueCreate(1024,1);netJobs=xQueueCreate(1,sizeof(NetJob));netReplies=xQueueCreate(1,sizeof(NetReply));
  if(!rxBytes || !netJobs || !netReplies){title("Not enough memory","Restart and contact support.");while(true)delay(1000);}
  if(SCANNER_TEST_ONLY)screen=SCANNER_TEST;
  else {
    storageFault=!restoreOutbox();
    WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);
    if(strlen(INVENTORY_WIFI_SSID))WiFi.begin(INVENTORY_WIFI_SSID,INVENTORY_WIFI_PASSWORD);
    if(storageFault || !outbox.empty()){suspended=true;screen=WAITING;}
    if(!calibrated){do{calibrated=calibrate();}while(!calibrated);}
    if(xTaskCreate(networkTask,"inventory-http",12288,nullptr,1,nullptr)!=pdPASS){storageFault=true;screen=WAITING;}
  }
  if(xTaskCreate(bluetoothTask,"scanner-spp",6144,nullptr,1,nullptr)!=pdPASS){title("Bluetooth task failed","Restart and contact support.");while(true)delay(1000);}
  draw();
#endif
}
void loop() {
#if DIAGNOSTICS_ONLY
  if(touch.touched()){
    auto p=touch.getPoint();lcd.fillRect(0,75,320,120,BG);lcd.setTextColor(FG,BG);
    lcd.drawString("Raw X: "+String(p.x),10,85,2);lcd.drawString("Raw Y: "+String(p.y),10,115,2);
    lcd.drawString("Pressure: "+String(p.z),10,145,2);delay(100);
  }
#else
  static bool wasWifi=false,wasBt=false,wasAuth=false,wasReady=false;
  bool wifi=WiFi.status()==WL_CONNECTED,bt=scanner.connected(0);
  if(bt!=wasBt){wasBt=bt;framer.reset();Serial.println(bt?"Scanner connected":"Scanner disconnected");draw();}
  if(wifi!=wasWifi){wasWifi=wifi;draw();}
  if(wasAuth!=btAuthFailed || wasReady!=btReady){wasAuth=btAuthFailed;wasReady=btReady;draw();}
  if(!SCANNER_TEST_ONLY && !wifi && strlen(INVENTORY_WIFI_SSID) && millis()-lastWifi>15000){lastWifi=millis();WiFi.reconnect();}
  scannerInput();
  if(!SCANNER_TEST_ONLY) {
    receiveReplies();
    if(screen==RESULT && !netBusy && millis()-resultAt>(resultSuccess?900UL:8000UL)){
      if(rejected){screen=PAUSED;draw();}
      else {input="";screen=SCAN_READY;draw();dispatch();}
    }
    if(!rejected)dispatch();
  }
  if(touch.touched() && calibrated && !netBusy){
    auto raw=touch.getPoint();
    int x=lroundf(transform[0]*raw.x+transform[1]*raw.y+transform[2]);
    int y=lroundf(transform[3]*raw.x+transform[4]*raw.y+transform[5]);
    int pressed=-1;
    for(int i=0;i<buttonCount;i++){auto b=buttons[i];if(x>=b.x && x<b.x+b.w && y>=b.y && y<b.y+b.h){pressed=b.id;break;}}
    waitRelease();if(pressed>=0)tap(pressed);
  }
#endif
  delay(5);
}
