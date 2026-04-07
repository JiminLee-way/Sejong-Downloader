# Sejong-Downloader

세종대학교 eCampus(집현캠퍼스) 강의 PDF 일괄 다운로드 CLI 도구

## 기능

- 강의 페이지의 모든 교안(PDF) 일괄 다운로드
- 시간 제한이 걸린 미공개 교안도 다운로드 가능
- 다운로드 금지 설정된 파일도 원본 PDF로 다운로드

### 제한사항

- 과제 내부의 PDF는 다운로드 불가
- 퀴즈/시험 문제는 다운로드 불가

## 설치

```bash
pip install .
```

## 사용법

```bash
sejong-dl -u [학번] -p [비밀번호] [강의 URL]
```

### 예시

```bash
# 기본 (./downloads 폴더에 저장)
sejong-dl -u 20XXXXXX -p mypassword https://ecampus.sejong.ac.kr/course/view.php?id=27323

# 저장 경로 지정
sejong-dl -u 20XXXXXX -p mypassword -o ./리눅스 https://ecampus.sejong.ac.kr/course/view.php?id=27323
```

### 옵션

| 옵션 | 설명 |
|------|------|
| `-u`, `--username` | 학번 (필수) |
| `-p`, `--password` | 비밀번호 (필수) |
| `-o`, `--output` | 다운로드 디렉토리 (기본: `./downloads`) |

## 의존성

- Python >= 3.10
- requests
- beautifulsoup4
