#include "scanner_protocol.h"
#include <cassert>
#include <iostream>

int main() {
  BarcodeFramer parser;std::string output;
  auto feed=[&](const std::string &data) {
    std::vector<std::string> codes;int invalid=0;
    for(unsigned char c:data) {
      auto result=parser.feed(c,output);
      if(result==FrameResult::Barcode)codes.push_back(output);
      if(result==FrameResult::Invalid)invalid++;
    }
    return std::make_pair(codes,invalid);
  };
  assert(feed("037600").first.empty());
  auto tail=feed("106184\r\n");
  assert(tail.first==std::vector<std::string>{"037600106184"});
  assert(tail.second==0);
  auto repeat=feed("037600106184\r037600106184\r");
  assert(repeat.first.size()==2); // same product scanned twice is two intentional operations
  assert(feed("ABC12345678\r").second==1);
  assert(feed("12345678901234567890\n").second==1);
  assert(feed("123\n").second==1);
  assert(feed("12345678\n\r\n").first.size()==1);
  feed("1234");parser.reset();assert(feed("5678\r").second==1);
  bool diskOk=true;std::vector<ScanRequest> disk;
  auto store=[&](const std::vector<ScanRequest>& value) {if(!diskOk)return false;disk=value;return true;};
  PersistentOutbox box(store);
  ScanRequest first{"/api/scan","same product, first operation","uuid-first"};
  ScanRequest second{"/api/scan","same product, second operation","uuid-second"};
  assert(box.append(first));assert(box.append(second));
  assert(box.front().id=="uuid-first");assert(disk.size()==2);
  // Lost reply/reboot restores the identical request rather than generating another ID.
  PersistentOutbox restarted(store);assert(restarted.restore(disk));
  assert(restarted.front().body==first.body && restarted.front().id==first.id);
  assert(!restarted.acknowledge("wrong reply"));
  diskOk=false;assert(!restarted.acknowledge(first.id));assert(restarted.size()==2);
  assert(!restarted.append(first));assert(restarted.size()==2);
  diskOk=true;assert(restarted.acknowledge(first.id));
  assert(restarted.front().id==second.id);
  assert(restarted.acknowledge(second.id));assert(disk.empty());
  for(unsigned int i=0;i<PersistentOutbox::capacity;i++)assert(box.append(first)==(i<PersistentOutbox::capacity-2));
  assert(box.size()==PersistentOutbox::capacity);
  assert(!box.append(second));assert(box.size()==PersistentOutbox::capacity);
  assert(!restarted.restore({{"/arbitrary","body","id"}}));
  std::cout<<"PASS: framing, CRLF, split packets, invalid/oversized frames, repeated products, durable FIFO, reboot replay, failed storage, mismatched reply, capacity limit.\n";
}
