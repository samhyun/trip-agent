"""외부 여행 데이터 provider.

각 provider는 실 API를 호출해 mock(`data/*.json`)과 동일한 스키마로 정규화한다.
키가 없거나 호출이 실패하면 호출부(travel_service)가 mock으로 폴백한다.
"""
