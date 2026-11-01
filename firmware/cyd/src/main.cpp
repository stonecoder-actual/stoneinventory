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
#if __has_include("stoneinventory_config.h")
#include "stoneinventory_config.h"
#else
#define INVENTORY_WIFI_SSID ""
#define INVENTORY_WIFI_PASSWORD ""
#define INVENTORY_API_BASE ""
#define INVENTORY_DEVICE_ID "kitchen-cyd-01"
#endif

TFT_eSPI lcd;
SPIClass touchSpi(VSPI);
XPT2046_Touchscreen touch(33,36);
Preferences prefs;
const uint16_t BG=0x1082, FG=TFT_WHITE, GREEN=0x2B68;
enum Screen { HOME, BARCODE, EDIT_COUNT, CONFIRM, WAITING, RESULT };
Screen screen=HOME;
String action, input, barcode, itemName, pending, resultText;
int oldCount=0;
unsigned long resultAt=0, lastWifi=0;
float transform[6];
bool calibrated=false;
struct Button { int x,y,w,h; String title; int id; };
Button buttons[16]; int buttonCount=0;

void title(String a, String b="") {
  lcd.fillScreen(BG); lcd.setTextColor(FG,BG);
  lcd.drawString(a.substring(0,26),10,8,2);
  lcd.drawString(b.substring(0,44),10,32,1); buttonCount=0;
}
void button(int x,int y,int w,int h,String text,int id,uint16_t color=GREEN) {
  lcd.fillRoundRect(x,y,w,h,5,color); lcd.setTextColor(FG,color);
  lcd.drawCentreString(text,x+w/2,y+(h-16)/2,2);
  if(buttonCount<16) buttons[buttonCount++]={x,y,w,h,text,id};
}
void draw();
void status(String text) {
  resultText=text; screen=RESULT; resultAt=millis(); draw();
}
void waitRelease() { while(touch.touched()) delay(20); delay(100); }

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
void retry() {
  if(!pending.length()) return;
  StaticJsonDocument<512> record;
  if(deserializeJson(record,pending)) { screen=WAITING;draw();return; }
  String path=record["path"].as<String>(), body=record["body"].as<String>();
  if(path!="/api/scan" && path!="/api/inventory/reconcile") { screen=WAITING;draw();return; }
  title("Contacting inventory server","Please wait. This may take a few seconds.");
  DynamicJsonDocument reply(2048);int code=0;
  bool parsed=request(path,body,reply,code);
  if(parsed && code==200 && reply["status"]=="success" && reply["inventory"]["after"].is<int>()) {
    StaticJsonDocument<384> sent;deserializeJson(sent,body);
    if(reply["request_id"].as<String>()!=sent["request_id"].as<String>()) { screen=WAITING;draw();return; }
    if(!prefs.remove("pending")) { screen=WAITING;draw();return; }
    pending="";
    String name=reply["product"]["name"] | "Unidentified product";
    status(name.substring(0,28)+"\n"+String(reply["inventory"]["before"].as<int>())+" -> "+
           String(reply["inventory"]["after"].as<int>())+"\nSaved on server");
  } else if(parsed && code>=400 && code<500) {
    if(!prefs.remove("pending")) { screen=WAITING;draw();return; }
    pending="";status(reply["detail"] | "Request rejected. Check web page.");
  } else { screen=WAITING;draw(); }
}
void sendOperation(int quantity) {
  StaticJsonDocument<384> body;
  body["barcode"]=barcode;body["quantity"]=quantity;body["device_id"]=INVENTORY_DEVICE_ID;
  body["request_id"]=uuid();
  String path="/api/scan";
  if(action=="edit") { path="/api/inventory/reconcile";body["expected_quantity"]=oldCount; }
  else body["action"]=action;
  String json;serializeJson(body,json);
  StaticJsonDocument<768> record;record["path"]=path;record["body"]=json;
  String saved;serializeJson(record,saved);
  if(prefs.putString("pending",saved)!=saved.length()) { status("Could not save safe retry.\nNothing sent.");return; }
  pending=saved;retry();
}
void submitBarcode() {
  if(input.length()<8 || input.length()>14) return;
  barcode=input;
  if(action!="edit") { sendOperation(1);return; }
  title("Reading current count","Inventory is stored on the server.");
  DynamicJsonDocument reply(2048);int code=0;
  if(!request("/api/products/"+barcode,"",reply,code) || code!=200 || !reply["quantity"].is<int>()) {
    status("Could not read product.\nCheck Wi-Fi or identify it\nin the web page first.");return;
  }
  oldCount=reply["quantity"].as<int>();itemName=reply["name"] | "Unidentified product";
  input="";screen=EDIT_COUNT;draw();
}
void keypad() {
  lcd.setTextColor(TFT_YELLOW,BG);lcd.drawString(input.length()?input:"_",12,52,2);
  for(int i=0;i<9;i++) button(10+(i%3)*65,80+(i/3)*38,60,33,String(i+1),i+1);
  button(10,194,60,33,"DEL",10);button(75,194,60,33,"0",0);button(140,194,60,33,"CLR",11);
  button(210,80,100,65,screen==BARCODE?"ENTER":"REVIEW",12);
  button(210,160,100,65,"CANCEL",13,0x8200);
}
void draw() {
  if(screen==HOME) {
    title("STONEINVENTORY",WiFi.status()==WL_CONNECTED?"Wi-Fi connected | Manual barcode input":"Wi-Fi not connected");
    button(10,65,145,65,"ADD",20);button(165,65,145,65,"REMOVE",21,0x8200);
    button(10,145,200,65,"EDIT COUNT",22);button(220,145,90,65,"CAL",23);
  } else if(screen==BARCODE || screen==EDIT_COUNT) {
    title(screen==BARCODE?"Enter barcode: "+action:"Actual package count",screen==EDIT_COUNT?"Current: "+String(oldCount)+" | "+itemName:"Include all digits, even leading zeros");
    keypad();
  } else if(screen==CONFIRM) {
    title("Confirm correction",itemName);
    lcd.setTextColor(FG,BG);lcd.drawCentreString(String(oldCount)+" -> "+input,160,80,4);
    lcd.drawCentreString("Correction, not consumption",160,120,2);
    button(10,170,145,55,"CANCEL",13,0x8200);button(165,170,145,55,"CONFIRM",24);
  } else if(screen==WAITING) {
    title("Change needs a reply","Do not rescan. The saved request will be retried.");
    lcd.setTextColor(FG,BG);lcd.drawString("Wi-Fi / server unavailable?",10,70,2);
    lcd.drawString("Retry uses the same request ID.",10,100,2);
    button(10,160,300,60,"RETRY SAFELY",25);
  } else {
    title("Inventory response");
    lcd.setTextColor(FG,BG);lcd.setCursor(10,65);lcd.setTextFont(2);lcd.println(resultText);
    button(10,180,300,50,"HOME",13);
  }
}
void tap(int id) {
  if(id==25) { retry();return; }
  if(id==13) { screen=HOME;input="";draw();return; }
  if(id>=20 && id<=22) { action=id==20?"add":id==21?"remove":"edit";input="";screen=BARCODE;draw();return; }
  if(id==23) { do { calibrated=calibrate(); } while(!calibrated);draw();return; }
  if(id==24) { sendOperation(input.toInt());return; }
  if(screen!=BARCODE && screen!=EDIT_COUNT) return;
  if(id==12) {
    if(screen==BARCODE) submitBarcode();
    else if(input.length() && input.toInt()<=1000000) { screen=CONFIRM;draw(); }
    return;
  }
  if(id==10) input.remove(input.length()?input.length()-1:0);
  else if(id==11) input="";
  else if(id>=0 && id<=9 && input.length()<(screen==BARCODE?14:7)) input+=String(id);
  draw();
}
void setup() {
  Serial.begin(115200);delay(300);
  lcd.init();lcd.setRotation(1);digitalWrite(21,HIGH);
  touchSpi.begin(25,39,32,33);touch.begin(touchSpi);touch.setRotation(1);
  Serial.println("StoneInventory CYD boot. Display profile: ILI9341, resistive XPT2046.");
#if DIAGNOSTICS_ONLY
  lcd.fillScreen(TFT_RED);delay(600);lcd.fillScreen(TFT_GREEN);delay(600);lcd.fillScreen(TFT_BLUE);delay(600);
  title("DISPLAY OK - touch the screen","Diagnostics only. No Wi-Fi or inventory requests.");
#else
  if(!prefs.begin("stoneinventory",false)) { title("Storage unavailable","Reboot; do not record inventory yet.");while(true) delay(1000); }
  pending=prefs.getString("pending","");
  calibrated=prefs.getBytesLength("touch")==sizeof(transform);
  if(calibrated) prefs.getBytes("touch",transform,sizeof(transform));
  WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);
  if(strlen(INVENTORY_WIFI_SSID)) WiFi.begin(INVENTORY_WIFI_SSID,INVENTORY_WIFI_PASSWORD);
  if(pending.length()) screen=WAITING;
  else if(!calibrated) { do { calibrated=calibrate(); } while(!calibrated); }
  draw();
#endif
}
void loop() {
#if DIAGNOSTICS_ONLY
  if(touch.touched()) {
    auto p=touch.getPoint();
    lcd.fillRect(0,75,320,120,BG);lcd.setTextColor(FG,BG);
    lcd.drawString("Raw X: "+String(p.x),10,85,2);
    lcd.drawString("Raw Y: "+String(p.y),10,115,2);
    lcd.drawString("Pressure: "+String(p.z),10,145,2);
    Serial.printf("touch x=%d y=%d pressure=%d\n",p.x,p.y,p.z);delay(100);
  }
#else
  static bool wasOnline=false;
  bool online=WiFi.status()==WL_CONNECTED;
  if(online!=wasOnline) { wasOnline=online;if(screen==HOME) draw(); }
  if(!online && strlen(INVENTORY_WIFI_SSID) && millis()-lastWifi>15000) { lastWifi=millis();WiFi.reconnect(); }
  if(screen==RESULT && millis()-resultAt>8000) { screen=HOME;draw(); }
  if(touch.touched() && calibrated) {
    auto raw=touch.getPoint();
    int x=lroundf(transform[0]*raw.x+transform[1]*raw.y+transform[2]);
    int y=lroundf(transform[3]*raw.x+transform[4]*raw.y+transform[5]);
    int pressed=-1;
    for(int i=0;i<buttonCount;i++) { auto b=buttons[i];if(x>=b.x && x<b.x+b.w && y>=b.y && y<b.y+b.h) { pressed=b.id;break; } }
    waitRelease();if(pressed>=0) tap(pressed);
  }
#endif
  delay(10);
}
