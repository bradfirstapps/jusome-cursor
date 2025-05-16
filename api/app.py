import os
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import requests
import re

load_dotenv()

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '../templates'),
    static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '../static')
)

KAKAO_REST_API_KEY = os.getenv('KAKAO_REST_API_KEY')
KAKAO_JAVASCRIPT_KEY = os.getenv('KAKAO_JAVASCRIPT_KEY')
MOIS_API_KEY = os.getenv('MOIS_API_KEY')
MOIS_ENG_API_KEY = os.getenv('MOIS_ENG_API_KEY')

@app.route('/')
def index():
    return render_template('index.html', kakao_javascript_key=KAKAO_JAVASCRIPT_KEY)

@app.route('/en')
def index_en():
    return render_template('index_en.html', kakao_javascript_key=KAKAO_JAVASCRIPT_KEY)

def parse_english_address(address):
    # 예: '2 Gajaeulmirae-ro' → 'Gajaeulmirae-ro 2'
    m = re.match(r'^(\d+)\s+([A-Za-z\-]+)', address)
    if m:
        return f"{m.group(2)} {m.group(1)}"
    return address

def is_english(text):
    return bool(re.match(r'^[A-Za-z0-9\-, ]+$', text))

@app.route('/convert', methods=['POST'])
def convert_address():
    data = request.json
    address = data.get('address', '').strip()
    page = data.get('page', 1)

    if not address:
        return jsonify({'error': '주소를 입력해주세요.'}), 400

    # 영문 주소 판별
    if is_english(address):
        # 영문 주소 API만 호출
        eng_url = 'https://www.juso.go.kr/addrlink/addrEngApi.do'
        eng_params = {
            'confmKey': MOIS_ENG_API_KEY,
            'currentPage': page,
            'countPerPage': 10,
            'keyword': address,
            'resultType': 'json'
        }
        eng_response = requests.get(eng_url, params=eng_params)
        juso_results = []
        total_count = 0
        juso_common = {}
        if eng_response.status_code == 200:
            eng_result = eng_response.json()
            print('영문주소 변환 응답(입력값):', eng_result)
            eng_common = eng_result.get('results', {}).get('common', {})
            total_count = int(eng_common.get('totalCount', '0'))
            juso_common = eng_common
            eng_list = eng_result.get('results', {}).get('juso', [])
            for eng in eng_list:
                kor_addr = eng.get('korAddr', '')
                juso_results.append({
                    'road_addr': eng.get('roadAddr', ''),
                    'jibun_addr': eng.get('jibunAddr', ''),
                    'eng_address': eng.get('roadAddr', '') or eng.get('engAddr', ''),
                    'kor_address': kor_addr,
                    'zip_no': eng.get('zipNo', '')
                })
        pagination = {
            'total_count': total_count,
            'current_page': int(juso_common.get('currentPage', '1')),
            'total_pages': (total_count + 9) // 10,
        }
        if not juso_results:
            return jsonify({'error': '주소 정보를 찾을 수 없습니다.', 'pagination': pagination}), 404
        if len(juso_results) == 1:
            result = {
                'addresses': juso_results,
                'pagination': pagination,
                'is_single_result': True
            }
            return jsonify(result)
        result = {
            'addresses': juso_results,
            'pagination': pagination,
            'is_single_result': False
        }
        return jsonify(result)

    # 한글 주소일 때는 도로명/지번(한글) API 결과만 반환
    korean_address = address
    tried_addresses = [address]
    juso_url = 'https://www.juso.go.kr/addrlink/addrLinkApi.do'
    juso_params = {
        'confmKey': MOIS_API_KEY,
        'currentPage': page,
        'countPerPage': 10,  # 한 페이지당 10개 결과
        'keyword': address,
        'resultType': 'json'
    }
    juso_response = requests.get(juso_url, params=juso_params)
    juso_results = []
    total_count = 0
    juso_common = {}
    has_korean_results = False
    if juso_response.status_code == 200:
        juso_result = juso_response.json()
        print('도로명/지번 주소 변환 응답:', juso_result)
        juso_common = juso_result.get('results', {}).get('common', {})
        total_count = int(juso_common.get('totalCount', '0'))
        current_page = int(juso_common.get('currentPage', '1'))
        juso_list = juso_result.get('results', {}).get('juso', [])
        if juso_list:
            has_korean_results = True
            for juso in juso_list:
                juso_results.append({
                    'road_addr': juso.get('roadAddr', ''),
                    'jibun_addr': juso.get('jibunAddr', ''),
                    'eng_address': juso.get('engAddr', ''),
                    'kor_address': juso.get('roadAddr', ''),
                    'zip_no': juso.get('zipNo', '')
                })
    pagination = {
        'total_count': total_count,
        'current_page': int(juso_common.get('currentPage', '1')),
        'total_pages': (total_count + 9) // 10,  # 올림 나눗셈 (10개씩 표시)
    }
    if not juso_results:
        return jsonify({'error': '주소 정보를 찾을 수 없습니다.', 'pagination': pagination}), 404
    if len(juso_results) == 1:
        result = {
            'addresses': juso_results,
            'pagination': pagination,
            'is_single_result': True
        }
        return jsonify(result)
    result = {
        'addresses': juso_results,
        'pagination': pagination,
        'is_single_result': False
    }
    return jsonify(result)

def query_address_detail(address):
    """주소 상세 정보를 조회하는 함수"""
    # 도로명/지번 주소로 검색
    juso_url = 'https://www.juso.go.kr/addrlink/addrLinkApi.do'
    juso_params = {
        'confmKey': MOIS_API_KEY,
        'currentPage': 1,
        'countPerPage': 1,
        'keyword': address,
        'resultType': 'json'
    }
    
    road_addr = jibun_addr = eng_addr_from_juso = kor_addr = zip_no = ''
    juso_response = requests.get(juso_url, params=juso_params)
    juso_found = False
    
    if juso_response.status_code == 200:
        juso_result = juso_response.json()
        print('도로명/지번 주소 변환 응답:', juso_result)
        juso_list = juso_result.get('results', {}).get('juso', [])
        if juso_list:
            juso_found = True
            road_addr = juso_list[0].get('roadAddr', '')
            jibun_addr = juso_list[0].get('jibunAddr', '')
            eng_addr_from_juso = juso_list[0].get('engAddr', '')
            kor_addr = road_addr
            zip_no = juso_list[0].get('zipNo', '')
    
    # 영문주소 변환 API
    eng_addr = eng_kor_addr = eng_road_addr = eng_jibun_addr = eng_zip_no = ''
    eng_url = 'https://www.juso.go.kr/addrlink/addrEngApi.do'
    eng_params = {
        'confmKey': MOIS_ENG_API_KEY,
        'currentPage': 1,
        'countPerPage': 1,
        'keyword': address,
        'resultType': 'json'
    }
    
    eng_response = requests.get(eng_url, params=eng_params)
    eng_found = False
    
    if eng_response.status_code == 200:
        eng_result = eng_response.json()
        print('영문주소 변환 응답(입력값):', eng_result)
        eng_list = eng_result.get('results', {}).get('juso', [])
        if eng_list:
            eng_found = True
            eng_addr = eng_list[0].get('roadAddr', '') or eng_list[0].get('engAddr', '')
            eng_kor_addr = eng_list[0].get('korAddr', '')
            eng_road_addr = eng_list[0].get('roadAddr', '')
            eng_jibun_addr = eng_list[0].get('jibunAddr', '')
            eng_zip_no = eng_list[0].get('zipNo', '')
            print('영문 API 우편번호 확인:', eng_zip_no)
    
    # 값 병합 (영문 API에서 값이 있으면 우선 사용하고, 없으면 도로명 API 값 사용)
    # 어느 한 API에서만 결과가 있어도 그 결과를 사용합니다
    if eng_found:
        # 영문 API에 결과가 있으면 영문 API의 결과 우선 사용
        if not road_addr:
            road_addr = eng_road_addr
        if not jibun_addr:
            jibun_addr = eng_jibun_addr
        if not kor_addr:
            kor_addr = eng_kor_addr
    elif juso_found:
        # 도로명 API에만 결과가 있는 경우
        if not eng_addr:
            eng_addr = eng_addr_from_juso
    
    # 우편번호 병합 (빈 문자열이면 다른 API 값 사용)
    if not zip_no:
        zip_no = eng_zip_no
    
    result = {
        'road_addr': road_addr or eng_road_addr,  # 둘 다 빈 문자열이면 빈 문자열 반환
        'jibun_addr': jibun_addr or eng_jibun_addr,
        'eng_address': eng_addr or eng_addr_from_juso,
        'kor_address': kor_addr or eng_kor_addr,
        'zip_no': zip_no or eng_zip_no,
        'zipNo': eng_zip_no or zip_no  # 추가: 프론트엔드에서 zipNo로도 접근 가능하도록
    }
    
    print('최종 반환 데이터:', result)
    
    # 결과가 유효한지 확인
    is_valid_result = (
        result['road_addr'] or 
        result['jibun_addr'] or 
        result['eng_address'] or 
        result['kor_address']
    )
    
    # 결과가 유효하지 않으면 오류 반환 대신 빈 객체를 반환
    if not is_valid_result:
        return {'error': '주소 정보를 찾을 수 없습니다.'}
        
    return result

@app.route('/geocode', methods=['POST'])
def geocode():
    data = request.json
    address = data.get('address')
    if not address:
        return jsonify({'error': '주소를 입력하세요.'}), 400
    url = 'https://dapi.kakao.com/v2/local/search/address.json'
    headers = {'Authorization': f'KakaoAK {KAKAO_REST_API_KEY}'}
    params = {'query': address}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return jsonify({'error': '카카오맵 API 호출 실패'}), 500
    result = response.json()
    documents = result.get('documents', [])
    if not documents:
        return jsonify({'error': '좌표를 찾을 수 없습니다.'}), 404
    x = documents[0].get('x')
    y = documents[0].get('y')
    return jsonify({'lat': y, 'lng': x})

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/en/about')
def about_en():
    return render_template('about_en.html', kakao_javascript_key=KAKAO_JAVASCRIPT_KEY)

@app.route('/en/privacy')
def privacy_en():
    return render_template('privacy_en.html', kakao_javascript_key=KAKAO_JAVASCRIPT_KEY)

@app.route('/en/contact')
def contact_en():
    return render_template('contact_en.html', kakao_javascript_key=KAKAO_JAVASCRIPT_KEY)

@app.route('/address_detail', methods=['POST'])
def address_detail():
    """선택한 주소의 상세 정보를 조회합니다."""
    data = request.json
    address = data.get('address', '').strip()
    address_type = data.get('type', 'road_addr')  # road_addr, jibun_addr, eng_address
    
    if not address:
        return jsonify({'error': '주소를 입력해주세요.'}), 400
    
    result = query_address_detail(address)
    
    # 오류가 있는지 확인
    if 'error' in result:
        return jsonify(result), 404
        
    return jsonify(result)

# 아래 부분을 제거 또는 주석 처리
#if __name__ == "__main__":
#    app.run(debug=True, host="0.0.0.0", port=5050) 