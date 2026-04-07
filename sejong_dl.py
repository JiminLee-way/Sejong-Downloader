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


def login(session: requests.Session, username: str, password: str) -> bool:
    login_url = f"{BASE_URL}/login/index.php"
    data = {
        "ssoGubun": "Login",
        "type": "popup_login",
        "username": username,
        "password": password,
    }
    resp = session.post(login_url, data=data, allow_redirects=True)
    if "loginerrormessage" in resp.text or "login/index.php" in resp.url:
        return False
    return True


def get_file_list(session: requests.Session, course_url: str) -> list[dict]:
    resp = session.get(course_url)
    if "login" in resp.url:
        print("[!] 세션이 만료되었습니다.")
        sys.exit(1)

    soup = BeautifulSoup(resp.text, "html.parser")
    files = []
    seen_ids = set()

    for link in soup.find_all("a", href=re.compile(r"/mod/ubfile/view\.php\?id=\d+")):
        href = link["href"]
        match = re.search(r"id=(\d+)", href)
        if not match:
            continue

        file_id = match.group(1)
        if file_id in seen_ids:
            continue
        seen_ids.add(file_id)

        name = link.get_text(strip=True)
        name = re.sub(r"\s*파일$", "", name).strip()
        if not name:
            name = f"file_{file_id}"

        files.append({"id": file_id, "name": name})

    return files


def download_pdf(session: requests.Session, file_id: str, output_path: str) -> bool:
    url = f"{BASE_URL}/local/ubdoc/download.php?id={file_id}&tp=m&pg=ubfile"
    resp = session.get(url, stream=True)

    if resp.status_code != 200 or "application/pdf" not in resp.headers.get(
        "content-type", ""
    ):
        return False

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return True


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip(". ") or "untitled"


def main():
    parser = argparse.ArgumentParser(
        description="세종대학교 eCampus 강의 PDF 일괄 다운로드",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="예시:\n  sejong-dl -u 20XXXXXX -p mypass https://ecampus.sejong.ac.kr/course/view.php?id=27323",
    )
    parser.add_argument("url", help="강의 페이지 URL")
    parser.add_argument("-u", "--username", required=True, help="학번")
    parser.add_argument("-p", "--password", required=True, help="비밀번호")
    parser.add_argument(
        "-o", "--output", default="./downloads", help="다운로드 디렉토리 (기본: ./downloads)"
    )

    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    )

    # 1. 로그인
    print("[*] 로그인 중...")
    if not login(session, args.username, args.password):
        print("[!] 로그인 실패. 학번/비밀번호를 확인하세요.")
        sys.exit(1)
    print("[+] 로그인 성공")

    # 2. 파일 목록
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
            print("FAIL (접근 제한)")

    print(f"\n[완료] {success}/{len(files)} 다운로드 성공 → {args.output}/")


if __name__ == "__main__":
    main()
