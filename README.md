# 카링&림보 알림이

선택한 모니터의 카링 게이지를 읽고 “빨간실 맞아요 / 초록실 맞아요 / 노란실 맞아요”로 안내하는 Windows 프로그램입니다.

## 실행 및 사용

1. 실행용 ZIP을 모두 풀고 **카링 알림이.exe**를 실행합니다.

   <img width="810" height="827" alt="image" src="https://github.com/user-attachments/assets/4a29d88e-2b4c-4cc9-9b0a-33b91e4477a2" />

3. 메이플스토리를 창모드 또는 테두리 없는 창모드로 엽니다.
   

4. **게이지 전체 영역 지정**을 누르고 게임이 있는 모니터를 선택합니다.

   <img width="344" height="187" alt="image" src="https://github.com/user-attachments/assets/6064190c-7dae-410b-95fc-f317c8a70873" />


6. 선택한 화면의 미리보기에서 아래 이미지처럼 게이지가 포함된 전체를 드래그합니다.

   <img width="188" height="225" alt="image" src="https://github.com/user-attachments/assets/47b22edb-6ed4-44c2-8146-00db48dd66b5" />
   <img width="422" height="331" alt="normal" src="https://github.com/user-attachments/assets/74b5b63a-4bc6-4626-a89f-e7781fe5d162" />



8. 상한·하한과 음성 간격을 입력하고 **설정 적용**을 누릅니다. 기본 기준은 800 이상 / 100 이하입니다.
9. 음량을 조절하고 **음성 테스트**로 확인한 뒤 **모니터링 시작**을 누릅니다.
10. 전투가 끝나거나 화면 위치를 바꿀 때는 **모니터링 종료**를 누릅니다. 창은 유지됩니다.


※ 주의사항 : 게임 창 위치, 화면 배율, 모니터 배치·해상도를 변경하면 영역을 다시 지정하세요. 알리미로 게이지를 가리지 마세요.
※ 림보 정화 게이지 또한 똑같은 방식으로 작동합니다.

## 설정

- 다크·라이트 모드, 글자 크기 80~130%, 음량 0~100%를 지원합니다.
- 음량 0%는 음소거입니다. 한국어 남성 InJoon 음성은 기본 대비 30% 빠릅니다. 파일이 포함되어 인터넷이나 별도 음성 설치가 필요하지 않습니다.
- 메이플스토리 Light/Bold 폰트가 포함됩니다.
- 항상 위에 표시의 기본값은 꺼짐입니다.
- 설정은 실행 파일 옆 `settings.json`에 저장됩니다. 업데이트 시 이 파일을 새 실행 파일 옆으로 복사하면 설정을 이어 쓸 수 있습니다.

## 작동방식

위쪽 숫자=혼돈(보라), 왼쪽=도올(초록), 오른쪽=궁기(노랑)로 구분합니다.

| 게이지 | 상한 이상 | 하한 이하 |
|---|---|---|
| 혼돈 | 빨간실 맞아요 | 노란실 맞아요 |
| 도올 | 노란실 맞아요 | 초록실 맞아요 |
| 궁기 | 초록실 맞아요 | 빨간실 맞아요 |

신뢰도 85% 이상 숫자 세 개가 3회 연속 확인될 때만 안내합니다.

## 소스로 실행

Windows, Python 3.10~3.12에서 소스 폴더를 열고 실행합니다. `assets`와 `fonts` 폴더가 필요합니다.

    python -m pip install -r requirements.txt
    python app.py

테스트:

    python -m unittest discover -s tests -v

테스트 25개 통과. 가장자리 일부가 덜 찬 합성 이미지와 짧은 발광에 대한 회귀 테스트를 포함합니다. 림보는 제공된 두 이미지와 크기·밝기 변형에서 확인했습니다. 실제 듀얼 모니터 UI 조작과 게임 중 통합 동작은 자동 실행 환경에서 검증하지 못했습니다. 전투 효과나 게이지 외형 변화에 따라 인식이 달라질 수 있습니다.

## 구성 요소

- OCR: [RapidOCR](https://github.com/RapidAI/RapidOCR)
- 화면 캡처: [MSS](https://python-mss.readthedocs.io/stable/)
- 음성 제작: Microsoft Edge 음성 서비스의 ko-KR-InJoonNeural, [edge-tts](https://github.com/rany2/edge-tts). 실행 중에는 이 서비스에 연결하지 않습니다.
- 폰트 출처 : 메이플스토리 서체 https://maplestory.nexon.com/media/font
- 폰트·아이콘·게이지 참고 이미지: 사용자가 제공한 자료
