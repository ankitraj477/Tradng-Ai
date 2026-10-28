---
name: build-cpp-scanner
description: Compile, optimize, and benchmark the high-performance C++ market scanner against the Python engine in Tradng-Ai.
---

# C++ Scanner Build & Benchmark Runbook

Use this skill when compiling [cpp/scanner.cpp](file:///c:/Users/KIIT/Desktop/projects/Tradng-Ai/cpp/scanner.cpp), configuring `cpp_scanner_path`, or evaluating scan cycle latency across the NIFTY 500 universe.

## Compilation Commands

### Linux / Oracle VM (Ubuntu & Oracle Linux)
```bash
sudo apt-get install -y g++ # or: sudo dnf install -y gcc-c++
g++ -O3 -std=c++17 cpp/scanner.cpp -o cpp/scanner
```

### Windows (GCC / MinGW or MSVC)
```powershell
g++ -O3 -std=c++17 cpp/scanner.cpp -o cpp/scanner.exe
# Or with MSVC:
cl.exe /O2 /std:c++17 cpp/scanner.cpp /Fe:cpp/scanner.exe
```

## Configuration
Once compiled, toggle C++ scanning in [config/default.json](file:///c:/Users/KIIT/Desktop/projects/Tradng-Ai/config/default.json):
```json
{
  "use_cpp_scanner": true,
  "cpp_scanner_path": "cpp/scanner"  // On Windows: "cpp/scanner.exe"
}
```

## Latency Benchmark Verification
Run the scanner performance regression test:
```powershell
.venv\Scripts\python.exe -m pytest tests/test_scanner_v8.py -v
```
Assert that screening 500 symbols completes in $< 200\text{ms}$ with zero memory leaks.
