import cv2                       # 0penCV函式庫:用來做影像處理
import numpy as np               # 陣列運算模組

from paddleocr import PaddleOCR  # OCR辨識模組
from opencc import OpenCC        # openCC函式庫:用來處理繁體中文與簡體中文轉換

import re                        # 正規表達式模組
from datetime import datetime, timedelta
import time
from sqlmodel import Session, desc, select
from model import OilPrice
from database import engine

"""
ocr = PaddleOCR(
    lang='ch',                              # 設定語言為中文
    ocr_version='PP-OCRv4',                 # 使用 PP-OCRv4 模型
    use_doc_orientation_classify=False,     # 不偵測文件旋轉角度，快速但需保證圖片方向正確
    use_doc_unwarping=False                 # 不做透視校正（去除傾斜），加快速度
    )
"""

ocr = PaddleOCR(
    lang='ch',
    ocr_version='PP-OCRv4',
    use_angle_cls=True
)

#ocr = PaddleOCR(use_angle_cls=True, lang='ch') # 初始化OCR


def extract_integers(word_list):
    """
    篩選出列表中的純整數數字
    """
    integer_list = []
    
    for word in word_list:
        # 使用 isdigit() 檢查字串是否只包含數字 (0-9)
        # 這樣會過濾掉帶有小數點的 32.4 或帶有橫線的日期
        if word.isdigit():
            integer_list.append(int(word)) # 轉成整數後儲存
            
    return integer_list


def ocr_recognize(file_location):

    result = {'日期':" ",'公升':' ','類型':' '}  # 用來存放結果:日期、數量、燃油種類

    Fuel_type = ['95無鉛','92無鉛','98無鉛', '超級柴油', '九五無鉛', '九二無鉛' ,'九八無鉛']

    Fuel_dict = {"95無鉛":"汽油", "92無鉛":"汽油", "98無鉛":"汽油", "超級柴油":"柴油", '九五無鉛':"汽油", '九八無鉛':"汽油", '九二無鉛':"汽油"}


    converter = OpenCC('s2t.json')
 

    results = ocr.predict(file_location) # 辨識結果: 回傳是一個 list

    # 正確地從 results[0] 中取得 rec_texts（辨識的文字）
    word_list = results[0]['rec_texts']

    # 將簡體中文轉成繁體中文
    index = 0
    for i in word_list:
        word_list[index] = converter.convert(word_list[index])
        index += 1

    # 將 word_list 轉成 string
    word_str = ' '.join(word_list)



    # 利用規則表達式尋找日期
    match = re.search(r'\d{4}-\d{2}-\d{2}', word_str) 

    # 如果有搜尋到日期則輸出
    if match:
        result['日期'] = match.group()



    invoice_date_str = result['日期']  # 發票日期
    invoice_date = datetime.strptime(invoice_date_str, "%Y-%m-%d")


    with Session(engine) as session:
        statement = (
            select(OilPrice)
            .where(OilPrice.publish_date <= invoice_date)
            .order_by(desc(OilPrice.publish_date))
            .limit(1)
        )

        data = session.execute(statement).scalar_one_or_none()
        

        # 偵測 Fuel_type 中的油品類型是否存在於辨識結果中，用來提取油品種類
        # matched_keyword 回傳符合的油品種類

        matched_keyword = None

        for item in results[0]['rec_texts']:
            for keyword in Fuel_type:
                if item in keyword:
                    matched_keyword = keyword
                    break  # 找到就跳出內層迴圈
            if matched_keyword:
                break  # 已找到就跳出外層迴圈

        result['類型'] = Fuel_dict[matched_keyword]

        
        
        for item in results[0]['rec_texts']:
            if "總計" in item:
                if matched_keyword in ["九二無鉛", "92無鉛"]:
                    result['公升'] = int(re.search(r'\d+', item).group()) / data.price_92
                if matched_keyword in ["九五無鉛", "95無鉛"]:
                    result['公升'] = int(re.search(r'\d+', item).group()) / data.price_95
                if matched_keyword in ["九八無鉛", "98無鉛"]:
                    result['公升'] = int(re.search(r'\d+', item).group()) / data.price_98
                if matched_keyword =="超級柴油":
                    result['公升'] = int(re.search(r'\d+', item).group()) / data.price_diesel

        '''
        integer_list = []
        
        for word in word_list:
            # 使用 isdigit() 檢查字串是否只包含數字 (0-9)
            # 這樣會過濾掉帶有小數點的 32.4 或帶有橫線的日期
            if word.isdigit():
                integer_list.append(int(word)) # 轉成整數後儲存
        
        print(integer_list)
        '''


        return result