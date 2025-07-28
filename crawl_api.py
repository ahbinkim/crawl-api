from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re
import math

app = Flask(__name__)

@app.route('/search', methods=['GET'])
def search_product():
    search_keyword = request.args.get('q', '').strip()
    if not search_keyword:
        return jsonify({'error': '검색어가 없습니다.'}), 400

    try:
        search_url = f'https://duksan.kr/products/prd_search.php?keyword={search_keyword}'
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(search_url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = [row for row in soup.select('tr[id]') if row.get('id').isdigit()]

        if not rows:
            return jsonify({'result': 'not_found'})

        first_row = rows[0]
        tds = first_row.find_all('td')

        stock_raw = tds[-2].text.strip().replace('\xa0', '').replace(' ', '')
        stock_parts = stock_raw.split('|')
        ansan_stock = stock_parts[0] if len(stock_parts) > 0 else '0'
        jincheon_stock = stock_parts[1] if len(stock_parts) > 1 else '0'
        stock_label = f"{ansan_stock}(안산재고) | {jincheon_stock}(진천재고)"

        price_raw = tds[-3].text
        price_digits = re.findall(r'\d+', price_raw.replace('\xa0', '').replace(',', ''))
        if price_digits:
            original_price = int(''.join(price_digits))
            discounted_price = math.ceil(original_price * 0.9 / 100) * 100  # 100원 단위로 올림
    
        return jsonify({
            'result': 'success',
            'product_code': search_keyword,
            'original_price': original_price,
            'discounted_price': discounted_price,
            'stock': {
                'ansan': ansan_stock,
                'jincheon': jincheon_stock,
                'label': stock_label
                }
            })
        return jsonify({'result': 'no_price'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
