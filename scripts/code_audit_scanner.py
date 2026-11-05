"""
Comprehensive Static Code Quality & Security Scanner for Tradng-Ai.
"""

import os
import ast
import re
import json

def scan_repository():
    findings = []
    files_catalog = []
    
    root_dir = os.path.abspath(".")
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Exclude directories
        if any(ex in dirpath for ex in [".git", ".venv", "__pycache__", ".pytest_cache", os.path.join("data", "cache")]):
            continue
            
        rel_dir = os.path.relpath(dirpath, root_dir)
        
        for file in filenames:
            filepath = os.path.join(dirpath, file)
            rel_path = os.path.relpath(filepath, root_dir)
            size = os.path.getsize(filepath)
            
            # Module category
            if rel_path.startswith("app" + os.sep + "broker"):
                cat = "broker"
            elif rel_path.startswith("app" + os.sep + "data"):
                cat = "data"
            elif rel_path.startswith("app" + os.sep + "fno"):
                cat = "fno"
            elif rel_path.startswith("app" + os.sep + "intraday"):
                cat = "intraday"
            elif rel_path.startswith("app" + os.sep + "ml"):
                cat = "ml"
            elif rel_path.startswith("app" + os.sep + "ops"):
                cat = "ops"
            elif rel_path.startswith("app" + os.sep + "swing"):
                cat = "swing"
            elif rel_path.startswith("app"):
                cat = "core"
            elif rel_path.startswith("tests"):
                cat = "tests"
            elif rel_path.startswith("scripts"):
                cat = "scripts"
            elif rel_path.startswith("config"):
                cat = "config"
            elif rel_path.startswith("cloud"):
                cat = "cloud"
            elif rel_path.startswith("docker"):
                cat = "docker"
            elif rel_path.startswith("docs"):
                cat = "docs"
            elif rel_path.startswith("cpp"):
                cat = "cpp"
            else:
                cat = "root"
                
            file_entry = {
                "file_path": rel_path.replace("\\", "/"),
                "category": cat,
                "size_bytes": size,
                "review_status": "reviewed",
                "modified": False,
                "findings": []
            }
            
            if file.endswith(".py"):
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    
                lines = content.splitlines()
                file_entry["lines"] = len(lines)
                
                # 1. AST Parsing
                try:
                    tree = ast.parse(content, filename=rel_path)
                except SyntaxError as e:
                    finding = {
                        "id": f"SYNTAX-{len(findings)+1}",
                        "type": "SYNTAX_ERROR",
                        "severity": "Critical",
                        "line": e.lineno,
                        "desc": str(e)
                    }
                    findings.append(finding)
                    file_entry["findings"].append(finding)
                    continue
                    
                # 2. Line by line pattern scans
                for idx, line in enumerate(lines, 1):
                    # Unsafe fetchone dict conversion without None check
                    if "dict(c.execute" in line and ".fetchone())" in line:
                        finding = {
                            "id": f"UNSAFE-FETCH-{len(findings)+1}",
                            "type": "UNSAFE_FETCHONE_DICT",
                            "severity": "Medium",
                            "line": idx,
                            "desc": f"Direct dict() cast on fetchone() without None guard: {line.strip()}"
                        }
                        findings.append(finding)
                        file_entry["findings"].append(finding)
                        
                    # Bare except
                    if re.match(r"^\s*except\s*:", line):
                        finding = {
                            "id": f"BARE-EXCEPT-{len(findings)+1}",
                            "type": "BARE_EXCEPT",
                            "severity": "Low",
                            "line": idx,
                            "desc": f"Bare except clause catches SystemExit and KeyboardInterrupt: {line.strip()}"
                        }
                        findings.append(finding)
                        file_entry["findings"].append(finding)
                        
                    # Hardcoded API keys or secrets
                    if any(k in line.lower() for k in ["api_key = \"", "secret = \"", "password = \""]) and not any(ok in line.lower() for ok in ["os.getenv", "os.environ", "get(", "mock"]):
                        finding = {
                            "id": f"SECRET-LITERAL-{len(findings)+1}",
                            "type": "HARDCODED_SECRET",
                            "severity": "High",
                            "line": idx,
                            "desc": f"Possible hardcoded secret literal: {line.strip()[:60]}"
                        }
                        findings.append(finding)
                        file_entry["findings"].append(finding)
                        
                    # Direct equality on token comparison
                    if "token ==" in line or "== token" in line or "== dashboard_token" in line:
                        finding = {
                            "id": f"TIMING-ATTACK-{len(findings)+1}",
                            "type": "TIMING_SIDE_CHANNEL",
                            "severity": "Medium",
                            "line": idx,
                            "desc": f"Direct string comparison on security token vulnerable to timing attack: {line.strip()}"
                        }
                        findings.append(finding)
                        file_entry["findings"].append(finding)
                        
            files_catalog.append(file_entry)
            
    print(f"Cataloged {len(files_catalog)} repository files.")
    print(f"Discovered {len(findings)} automated findings.")
    for f in findings:
        print(f"  [{f['severity']}] {f['type']} at line {f.get('line')}: {f['desc']}")
        
    return files_catalog, findings

if __name__ == "__main__":
    scan_repository()
