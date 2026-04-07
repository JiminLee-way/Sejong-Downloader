#!/usr/bin/env python3
"""sejong-ecampus-dl: 세종대학교 eCampus 강의 PDF 일괄 다운로드 CLI"""

import argparse
import re
import os
import sys
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://ecampus.sejong.ac.kr"
WORKER_URL = f"{BASE_URL}/local/ubdoc/worker.php"
DOWNLOAD_URL = f"{BASE_URL}/local/ubdoc/download.php"
IDOR_SCAN_RANGE = 30  # 기본 ID 앞뒤로 스캔할 범위


def create_session(username: str, password: str) -> requests.Session:
    """로그인된 세션 생성. 실패 시 프로그램 종료."""
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    )
    session._credentials = (username, password)

    if not _login(session, username, password):
        print("[!] 로그인 실패. 학번/비밀번호를 확인하세요.")
        sys.exit(1)

    return session


def _login(session: requests.Session, username: str, password: str) -> bool:
    """SSO 로그인 수행"""
    resp = session.post(
        f"{BASE_URL}/login/index.php",
        data={
            "ssoGubun": "Login",
            "type": "popup_login",
            "username": username,
            "password": password,
        },
        allow_redirects=True,
    )
    # 실패 시 login.php?errorcode=N 으로 리다이렉트
    return "errorcode" not in resp.url and "login.php" not in resp.url


def _ensure_session(session: requests.Session) -> None:
    """세션 만료 시 재로그인"""
    resp = session.get(f"{BASE_URL}/my/", allow_redirects=True)
    if "login" not in resp.url:
        return

    username, password = session._credentials
    print("[*] 세션 만료, 재로그인 중...")
    if not _login(session, username, password):
        print("[!] 재로그인 실패.")
        sys.exit(1)
    print("[+] 재로그인 성공")


def get_file_list(session: requests.Session, course_url: str) -> list[dict]:
    """강의 페이지에서 공개 파일 목록 + IDOR 스캔으로 비공개 파일까지 수집"""
    _ensure_session(session)

    resp = session.get(course_url)
    soup = BeautifulSoup(resp.text, "html.parser")

    files = {}  # id -> {id, name}

    # 1) 페이지에 노출된 파일 링크 수집
    for link in soup.find_all("a", href=re.compile(r"/mod/ubfile/view\.php\?id=\d+")):
        match = re.search(r"id=(\d+)", link["href"])
        if not match:
            continue
        file_id = match.group(1)
        if file_id in files:
            continue
        name = re.sub(r"\s*파일$", "", link.get_text(strip=True)).strip()
        files[file_id] = {"id": file_id, "name": name or f"file_{file_id}"}

    # 2) IDOR 스캔: 수집된 ID 범위 전후로 탐색
    if files:
        known_ids = sorted(int(fid) for fid in files)
        scan_start = min(known_ids) - 5
        scan_end = max(known_ids) + IDOR_SCAN_RANGE

        print(f"[*] IDOR 스캔 중 (ID {scan_start}~{scan_end})...")
        for fid in range(scan_start, scan_end + 1):
            fid_str = str(fid)
            if fid_str in files:
                continue
            info = _check_file(session, fid_str)
            if info:
                files[fid_str] = info

    return sorted(files.values(), key=lambda f: int(f["id"]))


def _check_file(session: requests.Session, file_id: str) -> dict | None:
    """worker.php로 파일 존재 여부 확인"""
    try:
        resp = session.post(
            WORKER_URL,
            data={"job": "checkState", "id": file_id, "tp": "m", "pg": "ubfile"},
            timeout=5,
        )
        data = resp.json()
        if data.get("state_code") == "100":
            name = data.get("file_realname") or data.get("file_name") or f"file_{file_id}"
            return {"id": file_id, "name": name}
    except (requests.RequestException, ValueError):
        pass
    return None


def download_pdf(session: requests.Session, file_id: str, output_path: str) -> bool:
    """PDF 다운로드. 세션 만료 시 재로그인 후 재시도."""
    for attempt in range(2):
        resp = session.get(
            f"{DOWNLOAD_URL}?id={file_id}&tp=m&pg=ubfile", stream=True, timeout=30
        )

        if resp.status_code == 200 and "pdf" in resp.headers.get("content-type", ""):
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True

        # 첫 시도 실패 시 재로그인 후 재시도
        if attempt == 0:
            _ensure_session(session)
        else:
            return False
    return False


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip(". ") or "untitled"


def main():
    parser = argparse.ArgumentParser(
        description="세종대학교 eCampus 강의 PDF 일괄 다운로드",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  sejong-dl -u 20XXXXXX -p mypass https://ecampus.sejong.ac.kr/course/view.php?id=27323\n"
            "  sejong-dl -u 20XXXXXX -p mypass -o ./리눅스 https://ecampus.sejong.ac.kr/course/view.php?id=27323"
        ),
    )
    parser.add_argument("url", help="강의 페이지 URL")
    parser.add_argument("-u", "--username", required=True, help="학번")
    parser.add_argument("-p", "--password", required=True, help="비밀번호")
    parser.add_argument(
        "-o", "--output", default="./downloads", help="다운로드 디렉토리 (기본: ./downloads)"
    )

    args = parser.parse_args()

    # 1. 로그인
    print("[*] 로그인 중...")
    session = create_session(args.username, args.password)
    print("[+] 로그인 성공")

    # 2. 파일 목록 (공개 + IDOR 스캔)
    print("[*] 파일 목록 수집 중...")
    files = get_file_list(session, args.url)

    if not files:
        print("[!] 다운로드할 파일이 없습니다.")
        sys.exit(0)

    print(f"[+] {len(files)}개 파일 발견")
    for i, f in enumerate(files, 1):
        print(f"    {i}. {f['name']}")

    # 3. 다운로드
    os.makedirs(args.output, exist_ok=True)
    success = 0

    for i, f in enumerate(files, 1):
        pdf_name = sanitize_filename(f["name"])
        if not pdf_name.lower().endswith(".pdf"):
            pdf_name += ".pdf"
        output_path = os.path.join(args.output, pdf_name)

        print(f"[{i}/{len(files)}] {f['name']} ... ", end="", flush=True)

        if download_pdf(session, f["id"], output_path):
            size_kb = os.path.getsize(output_path) / 1024
            print(f"OK ({size_kb:.0f}KB)")
            success += 1
        else:
            print("FAIL")

    print(f"\n[완료] {success}/{len(files)} 다운로드 성공 → {args.output}/")


if __name__ == "__main__":
    main()
