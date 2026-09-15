# 공항 주차장 실시간 현황·추세

김포·김해·제주공항에 갈 때 **어느 주차장에 댈지** 출발 직전에 판단하기 위한 휴대폰용 웹앱.

같은 공항이라도 주차장별 상황이 크게 다르다. 2026-09-15 10:13 실측에서 김포 국내선 제1주차장은 잔여 0면이었지만 국제선 주차빌딩은 161면이 비어 있었다.

## 현재 상태

설계 완료, 구현 전. 설계 문서는 [`docs/superpowers/specs/2026-09-15-airport-parking-app-design.md`](docs/superpowers/specs/2026-09-15-airport-parking-app-design.md).

`probe/`에 있는 것은 설계 판단을 위한 실측 도구다. 앱 코드가 아니다.

## 데이터 출처

한국공항공사 **전국공항 실시간 주차정보** (공공데이터포털, 데이터셋 15056803)

```
GET https://apis.data.go.kr/B551178/parking-realtime-status/info
```

실측으로 확인한 특성:

- 원천은 **정확히 60초마다** 갱신된다 (41분간 40회 연속, 편차 0)
- `schAirportCode`를 생략하면 **1회 호출로 전국 25개 주차장**이 모두 온다
- **점유율이 100%에 닿으면 카운터가 고정된다.** 만차 주차장의 입출차 정보는 신뢰할 수 없다

## 구조

```
data/lot_access.json    주차장별 도보·셔틀 접근성 (API로 오지 않는 정적 정보)
docs/reference/         한국공항공사 OpenAPI 활용가이드 원본
docs/superpowers/specs/ 설계 문서
probe/                  갱신주기·변화량 실측 도구
```

## 설정

서비스키는 공공데이터포털에서 발급받는다.

```
cp probe/.env.example probe/.env    # 값을 채운다
python probe/measure_refresh.py --once
```

`.env`는 `.gitignore`로 제외된다. 키를 커밋하거나 브라우저로 보내지 않는다.

## 보안 결정 기록

**인증을 두지 않는다.** 다루는 데이터가 전부 공공데이터이고 개인정보나 내부 정보가 없다. 저장소도 공개로 둔다 (GitHub Actions 무료 실행 시간과 Pages 사용을 위해).

**단, 서비스키는 예외다.** 휴대폰 브라우저에서 `data.go.kr`을 직접 호출하면 키가 노출되므로, 수집기(GitHub Actions)만 키를 쥐고 앱은 수집 결과 정적 파일만 읽는다. 키는 GitHub Secrets에만 둔다.
