# gunicorn 은 실행 위치의 이 파일을 자동으로 읽는다.


def post_worker_init(worker):
    """워커가 앱을 불러온 직후, 그 워커 안에서 잠들지 않기 스레드와 첫 수집을 시작한다."""
    from elearning.web import start_keepalive

    start_keepalive()
