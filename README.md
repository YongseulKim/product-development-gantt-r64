# 상품개발 간트차트 R64

단일 HTML과 Python 표준 라이브러리 서버로 구성된 일정 관리 도구입니다. 선후행 일정, 업무 차수, 회의 예정/확정, 실행 취소, HTML 저장·불러오기를 지원합니다.

이 저장소는 공개용 사본입니다. 초기 데이터와 테스트 사례는 예시이며, 실제 채널 원문·실명·운영 DB·내부 검수 증거는 포함하지 않습니다.

## 실행

Python 3.9 이상이 필요합니다. 별도 Python 패키지는 필요하지 않습니다.

```sh
git clone https://github.com/YongseulKim/product-development-gantt-r64.git
cd product-development-gantt-r64
python server/server.py --port 8000
```

`http://localhost:8000`에 접속합니다. macOS/Linux에서 명령이 `python3`이면 위 명령을 바꿉니다. 서버는 기본적으로 모든 네트워크 인터페이스에서 수신합니다.

`index.html`은 파일로 직접 열 수 있는 작업 사본이며 `server/index.html`은 같은 내용의 서버용 사본입니다. 수정할 때 두 파일을 동일하게 유지합니다.

## 다른 PC에서 이어서 작업

작업 시작 전 `git pull --ff-only`, 작업 종료 후 변경한 파일을 커밋하고 `git push`합니다. 실제 상품 데이터는 `server/data/`에 저장되며 Git에서 제외합니다. 기존 일정은 앱의 HTML 저장·불러오기를 이용하거나 서버 종료 후 data 폴더를 별도로 옮깁니다.

Termux 입력기/XFCE 설정과 계정 인증정보는 이 프로젝트에 포함하지 않습니다. 다른 PC에서는 자체 입력기와 브라우저를 사용합니다.

## 검수

서버 검수는 Python, 날짜/구문 검수는 Node.js가 필요합니다. 브라우저 검수에는 Chrome/Chromium과 같은 주 버전의 ChromeDriver가 필요합니다.

```sh
python tests/server_smoke.py
python tests/frontend_checks.py
python tests/browser_smoke.py
python tests/revision_scenarios.py
```

브라우저를 자동 탐색하지 못하면 `CHROME_BINARY`와 `CHROMEDRIVER_BINARY` 환경변수에 실행 파일의 절대 경로를 지정합니다. Windows PowerShell 예시는 다음과 같습니다.

```powershell
$env:CHROME_BINARY = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$env:CHROMEDRIVER_BINARY = 'C:\tools\chromedriver.exe'
python tests/browser_smoke.py
```

검수는 임시 데이터와 프로필을 사용합니다. 22개 업무 시나리오는 [검수 계획](docs/TESTING.md)을 참고하세요. 현행 규칙과 맞지 않는 사례는 전체 통과로 처리하지 않습니다.

## 알려진 사항

- 상품위원회는 부서장협의회 이후 최소 5영업일을 강제합니다. 더 짧은 간격의 명시적 일정은 입력할 수 없습니다.
- 판매개시일 기본 계산은 상품위원회 일자로부터 10영업일 뒤입니다. 기존 저장 날짜는 유지하며, 위원회 지연 시 판매준비 필수 업무의 종료일도 함께 반영합니다.
- 선행 지연은 후행에 전파되지만, 선행을 앞당겨도 후행을 자동으로 당기지 않습니다.
- 새로 추가하는 차수는 선행 연결 없이 생성하고 날짜를 직접 관리합니다. 기존 업무가 새 차수로 자동 연결되거나 후속 차수가 함께 생성되지 않습니다.
- 복수 시행일·공동 회의 동기화·공유 자료 버전·담당자/하위업무 전용 모델은 없습니다. 개별 업무와 메모로 일부 표현할 수 있습니다.
- 기준일 세로선은 표시용입니다. 기준일을 바꾸려면 상단 날짜 표지를 드래그합니다.
- tests/revision_scenarios.py의 일부 단계는 DOM/fixture 준비를 사용하며 모든 사용자 입력을 물리적 키보드·마우스로 재현한 것은 아닙니다.

공개 저장소의 변경은 원래의 로컬 내부 자료 사본에 자동 반영되지 않습니다. 수정할 때 어떤 사본인지 확인하세요.
