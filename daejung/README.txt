# 대정 크롤러 API (Render에 올리기, 쉬운 버전)

## 준비물
- GitHub 계정
- Render 계정 (무료 플랜 가능)

## 1단계: 이 폴더를 GitHub에 올리기
1) GitHub 접속 → 오른쪽 위 **+** → **New repository**
2) Repository 이름 아무거나 입력 → **Create repository**
3) 새 페이지에서 **"uploading an existing file"** 클릭
4) 이 폴더의 모든 파일을 드래그&드롭해서 업로드
   - app.py
   - daejung_crawl_pw_regonly.py
   - requirements.txt
   - Dockerfile
5) 맨 아래 **Commit changes** 클릭

## 2단계: Render에 연결해서 배포
1) Render 접속 → **New** → **Web Service**
2) **Build from a Git repository** 선택 → GitHub 연결 → 방금 만든 리포 선택
3) 나머지는 기본값 그대로 두고 **Create Web Service** 클릭
   - Render가 자동으로 Dockerfile을 감지합니다.
   - 몇 분 후 "Live"가 되면 배포 완료!

## 3단계: API 확인
- 헬스 체크
  - 브라우저 주소창에 `https://<서비스주소>.onrender.com/healthz` 입력 → `{"ok": true}` 나오면 정상
- 검색
  - `https://<서비스주소>.onrender.com/search?kw=5062-8825`
  - 첫 결과만 원하면 `&first_only=true` 붙이기

## 자주 묻는 질문
- **에러가 나요(브라우저 관련)** → 우리는 Playwright가 포함된 Docker 이미지를 사용해서 보통 해결됩니다.
- **검색이 비어요** → 검색어가 실제 사이트에서 결과가 있어야 합니다. 또는 사이트가 잠시 느릴 수 있어요. 잠깐 후 다시 시도해보세요.
- **labels가 빈 배열이에요** → 해당 제품 팝업에 규제 문구가 없으면 빈 배열이 정상입니다.

## 끝! 🎉
문구 그대로 따라 하시면 됩니다. 막히는 부분이 있으면 캡처와 함께 질문 주세요.
