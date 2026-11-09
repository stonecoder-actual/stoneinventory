#pragma once
#include <functional>
#include <string>
#include <vector>

enum class FrameResult { None, Barcode, Invalid };
class BarcodeFramer {
  std::string digits;
  bool invalid=false;
 public:
  void reset() { digits.clear();invalid=false; }
  bool hasPartial() const { return !digits.empty() || invalid; }
  FrameResult feed(unsigned char byte,std::string &output) {
    if(byte=='\r' || byte=='\n') {
      if(digits.empty() && !invalid) return FrameResult::None;
      bool good=!invalid && digits.size()>=8 && digits.size()<=14;
      output=digits;reset();
      return good?FrameResult::Barcode:FrameResult::Invalid;
    }
    if(byte<'0' || byte>'9' || digits.size()>=14) invalid=true;
    if(!invalid) digits.push_back(char(byte));
    return FrameResult::None;
  }
};
struct ScanRequest { std::string path,body,id; };
class PersistentOutbox {
 public:
  static constexpr size_t capacity=8;
  using Store=std::function<bool(const std::vector<ScanRequest>&)>;
 private:
  std::vector<ScanRequest> records;
  Store store;
 public:
  explicit PersistentOutbox(Store writer):store(writer) {}
  bool restore(const std::vector<ScanRequest>& saved) {
    if(saved.size()>capacity) return false;
    for(const auto &r:saved) if(r.id.empty() || r.body.empty() ||
      (r.path!="/api/scan" && r.path!="/api/inventory/reconcile")) return false;
    records=saved;return true;
  }
  bool append(const ScanRequest &request) {
    if(records.size()>=capacity) return false;
    auto candidate=records;candidate.push_back(request);
    if(!store(candidate)) return false;
    records=std::move(candidate);return true;
  }
  bool acknowledge(const std::string &id) {
    if(records.empty() || records.front().id!=id) return false;
    auto candidate=records;candidate.erase(candidate.begin());
    if(!store(candidate)) return false;
    records=std::move(candidate);return true;
  }
  size_t size()const{return records.size();}
  bool empty()const{return records.empty();}
  const ScanRequest &front()const{return records.front();}
};
