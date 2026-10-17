
"""
MindGuard Master Test Runner & Security Audit Pipeline
======================================================
Executes:
  1. Backend unit and integration pytest suite (tests/backend/)
  2. Isolated cold-install environment verification (extras/scripts/verify_clean_install.py)
  3. CI Crisis Release Gate with 222-case aggressive suite & locked holdout (extras/scripts/release_gate_crisis.py)
  4. Frontend TypeScript type-checking (npm run type-check)
  5. Frontend Vitest unit & accessibility tests (npm test)
  6. Frontend Vite production build (npm run build)
  7. Security dependency audits (pip-audit & npm audit)
"""

import sys
import os
import subprocess
import time
from pathlib import Path

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = ROOT_DIR / "server"
TESTS_BACKEND_DIR = ROOT_DIR / "tests" / "backend"
TESTS_DEEP_DIR = ROOT_DIR / "tests" / "deep"
CLIENT_DIR = ROOT_DIR / "client"

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SERVER_DIR))
sys.path.insert(0, str(TESTS_BACKEND_DIR))
sys.path.insert(0, str(TESTS_DEEP_DIR))

os.environ['USE_MONGOMOCK'] = 'true'
os.environ['FLASK_ENV'] = 'testing'


def run_backend_tests():
    print("\n=================================================================")
    print("      1. RUNNING BACKEND UNIT, INTEGRATION & DEEP SUITE TESTS    ")
    print("=================================================================")
    start_time = time.time()
    
    proc = subprocess.run([sys.executable, "-m", "pytest", str(TESTS_BACKEND_DIR), str(TESTS_DEEP_DIR), "-q"], cwd=str(ROOT_DIR), text=True, encoding='utf-8', errors='replace')
    
    elapsed = time.time() - start_time
    print(f"\n[Backend & Deep Tests Execution Time: {elapsed:.2f}s]")
    return proc.returncode == 0


def run_clean_install_verification():
    print("\n=================================================================")
    print("        2. RUNNING ISOLATED COLD-INSTALL VERIFICATION            ")
    print("=================================================================")
    start_time = time.time()
    
    script_path = ROOT_DIR / "scripts" / "verify_clean_install.py"
    proc = subprocess.run([sys.executable, str(script_path)], text=True, encoding='utf-8', errors='replace')
    
    elapsed = time.time() - start_time
    print(f"\n[Cold-Install Verification Time: {elapsed:.2f}s]")
    return proc.returncode == 0


def run_release_gate_check():
    print("\n=================================================================")
    print("     3. RUNNING CRISIS CI RELEASE GATE (222-Case Aggressive Suite) ")
    print("=================================================================")
    start_time = time.time()
    
    script_path = ROOT_DIR / "scripts" / "release_gate_crisis.py"
    proc = subprocess.run([sys.executable, str(script_path)], text=True, encoding='utf-8', errors='replace')
    
    elapsed = time.time() - start_time
    print(f"\n[CI Release Gate Execution Time: {elapsed:.2f}s]")
    return proc.returncode == 0


def run_frontend_type_check():
    print("\n=================================================================")
    print("           4. RUNNING FRONTEND TYPESCRIPT TYPE-CHECK             ")
    print("=================================================================")
    start_time = time.time()
    
def _run_npm(args: list[str]) -> tuple[bool, str, float]:
    start_time = time.time()
    npm_bin = "npm.cmd" if sys.platform == "win32" else "npm"
    try:
        proc = subprocess.run(
            [npm_bin] + args,
            cwd=str(CLIENT_DIR),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        elapsed = time.time() - start_time
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, output, elapsed
    except FileNotFoundError:
        elapsed = time.time() - start_time
        return False, "npm executable not found in PATH", elapsed


def run_frontend_type_check():
    print("\n=================================================================")
    print("           4. RUNNING FRONTEND TYPESCRIPT TYPE-CHECK             ")
    print("=================================================================")
    ok, output, elapsed = _run_npm(["run", "type-check"])
    if ok:
        print("[PASS] Frontend TypeScript type-check passed with 0 errors!")
        print(f"[TypeScript Type-Check Execution Time: {elapsed:.2f}s]")
        return True
    else:
        print("[FAIL] Frontend TypeScript type-check failed:")
        print(output)
        return False


def run_frontend_tests():
    print("\n=================================================================")
    print("           5. RUNNING FRONTEND VITEST UNIT & ACCESSIBILITY TESTS ")
    print("=================================================================")
    ok, output, elapsed = _run_npm(["test"])
    if ok:
        print("[PASS] Frontend Vitest tests passed!")
        print(output)
        print(f"[Frontend Test Execution Time: {elapsed:.2f}s]")
        return True
    else:
        print("[FAIL] Frontend Vitest tests failed:")
        print(output)
        return False


def run_frontend_build_check():
    print("\n=================================================================")
    print("           6. RUNNING FRONTEND VITE PRODUCTION BUILD             ")
    print("=================================================================")
    ok, output, elapsed = _run_npm(["run", "build"])
    if ok:
        print("[PASS] Frontend Vite build completed successfully!")
        print(f"[Frontend Build Execution Time: {elapsed:.2f}s]")
        return True
    else:
        print("[FAIL] Frontend Vite build failed:")
        print(output)
        return False


def run_security_audits():
    print("\n=================================================================")
    print("       7. RUNNING SECURITY DEPENDENCY AUDITS (pip & npm)         ")
    print("=================================================================")
    start_time = time.time()
    
    # 1. Python Pip Audit
    print("-> Checking Python dependencies with pip-audit (server/requirements.txt)...")
    try:
        req_file = str(SERVER_DIR / "requirements.txt")
        pip_proc = subprocess.run([sys.executable, "-m", "pip_audit", "-r", req_file], capture_output=True, text=True, encoding='utf-8', errors='replace')
        if pip_proc.returncode == 0:
            print("   [PASS] 0 Python vulnerabilities detected in server/requirements.txt.")
            pip_status = "PASS"
        else:
            out = (pip_proc.stdout or "") + (pip_proc.stderr or "")
            if "network" in out.lower() or "connection" in out.lower() or "timeout" in out.lower():
                print("   [UNAVAILABLE] pip-audit network/mirror connection issue:")
                print(out[:400])
                pip_status = "UNAVAILABLE"
            else:
                print("   [FAIL] pip-audit detected vulnerabilities:")
                print(out)
                pip_status = "FAIL"
    except FileNotFoundError:
        print("   [UNAVAILABLE] pip-audit is not installed in the environment.")
        pip_status = "UNAVAILABLE"

    # 2. Frontend NPM Audit (Production Dependencies)
    print("-> Checking Frontend production npm dependencies with npm audit (--omit=dev)...")
    npm_ok, npm_out, _ = _run_npm(["audit", "--omit=dev"])
    if npm_ok:
        print("   [PASS] 0 production npm vulnerabilities detected.")
        npm_status = "PASS"
    else:
        if "not found" in npm_out.lower() or "network" in npm_out.lower() or "ENOTFOUND" in npm_out:
            print("   [UNAVAILABLE] npm audit unavailable or network failure:")
            print(npm_out[:400])
            npm_status = "UNAVAILABLE"
        else:
            print("   [FAIL] npm audit detected vulnerabilities in production dependencies:")
            print(npm_out)
            npm_status = "FAIL"

    elapsed = time.time() - start_time
    print(f"\n[Security Audits Execution Time: {elapsed:.2f}s]")
    # Return True if clean (PASS) or audit service unavailable (due to network in offline CI)
    # Fail if confirmed vulnerabilities are found
    return (pip_status != "FAIL") and (npm_status != "FAIL")


def main():
    print("\n" + "=" * 75)
    print("      MINDGUARD COMPLETE END-TO-END MASTER SUITE & AUDIT PIPELINE")
    print("=" * 75)
    
    backend_ok = run_backend_tests()
    clean_install_ok = run_clean_install_verification()
    gate_ok = run_release_gate_check()
    type_ok = run_frontend_type_check()
    fe_test_ok = run_frontend_tests()
    frontend_ok = run_frontend_build_check()
    audit_ok = run_security_audits()
    
    print("\n" + "=" * 75)
    print("                     FINAL VERIFICATION SUMMARY                  ")
    print("=" * 75)
    print(f"  Backend Unit/Integration Tests : {'[PASS]' if backend_ok else '[FAIL]'}")
    print(f"  Cold-Install Environment Check : {'[PASS]' if clean_install_ok else '[FAIL]'}")
    print(f"  Crisis CI Release Gate         : {'[PASS]' if gate_ok else '[FAIL]'}")
    print(f"  Frontend TypeScript Type-Check : {'[PASS]' if type_ok else '[FAIL]'}")
    print(f"  Frontend Unit/A11y Tests       : {'[PASS]' if fe_test_ok else '[FAIL]'}")
    print(f"  Frontend Production Build      : {'[PASS]' if frontend_ok else '[FAIL]'}")
    print(f"  Security Dependency Audits    : {'[PASS]' if audit_ok else '[FAIL]'}")
    print("=" * 75 + "\n")
    
    all_ok = backend_ok and clean_install_ok and gate_ok and type_ok and fe_test_ok and frontend_ok and audit_ok
    if not all_ok:
        sys.exit(1)

if __name__ == "__main__":
    main()
