'''
# 修正後的 OCR 模組
import cv2
import numpy as np
from paddleocr import PaddleOCR
from opencc import OpenCC
import re
import os

def ocr_recognize(file_location):
    result = {'日期': " ", '公升': ' ', '類型': ' '}
    Fuel_conversion_chart = [['95無鉛', '92無鉛', '98無鉛'], '超級柴油']
    converter = OpenCC('s2t.json')
    
    # 確保 OCR 模組只需初始化一次，否則會增加延遲
    # 建議將 OCR 的初始化放在全域變數或 app 的啟動事件中
    ocr = PaddleOCR(use_angle_cls=True, lang='ch')

    try:
        results = ocr.predict(file_location) # 使用 ocr 函數，它回傳的結構更標準
        
        # 檢查 results 是否為空或沒有足夠的數據
        if not results or not results[0]:
            print("OCR 辨識結果為空，可能圖片無法辨識")
            return {"日期": "無法辨識", "公升": "無法辨識", "類型": "無法辨識"}

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
            result['日期'] = match




        # 擷取購買資訊
        data = []
        try:
            # 尋找包含「品名」的行
            start_index = next((i for i, text in enumerate(word_list) if '品名' in text), -1)
            if start_index != -1:
                # 取得從「品名」開始的後續 7 個元素
                data = word_list[start_index : start_index + 7]
        except StopIteration:
            pass # 如果沒有找到「品名」，data 保持空列表

        # 輸出品名及數量，並檢查列表長度
        if len(data) >= 5:
            result['公升'] = data[4]
            if data[3] in Fuel_conversion_chart[0]:
                result['類型'] = '汽油'
            elif data[3] == Fuel_conversion_chart[1]:
                result['類型'] = '柴油'
        else:
            result['公升'] = '未找到'
            result['類型'] = '未找到'

    except Exception as e:
        print(f"OCR 處理發生錯誤: {e}")
        return {"日期": "處理錯誤", "公升": "處理錯誤", "類型": "處理錯誤"}
    
    if os.path.exists(file_location):
            os.remove(file_location)
        
    return result
'''


import cv2                       # 0penCV函式庫:用來做影像處理
import numpy as np               # 陣列運算模組

from paddleocr import PaddleOCR  # OCR辨識模組
from opencc import OpenCC        # openCC函式庫:用來處理繁體中文與簡體中文轉換

import re                        # 正規表達式模組

def ocr_recognize(file_location):

    result = {'日期':" ",'公升':' ','類型':' '}  # 用來存放結果:日期、數量、燃油種類

    Fuel_conversion_chart = [['95無鉛','92無鉛','98無鉛'], '超級柴油']


    converter = OpenCC('s2t.json')
 

    ocr = PaddleOCR(use_angle_cls=True, lang='ch') # 初始化OCR

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



    index = 0
    data = [] # 儲存購買資訊
    # 擷取購買資訊
    for i in word_list:
        if '品名' in i:
            for j in word_list[index:index+7]:
                data.append(j)
            break
        index += 1

    # 輸出品名及數量
    result['公升'] = data[4]
    if data[3] == Fuel_conversion_chart[1]:
        result['類型'] = '柴油'
    else :
        result['類型'] = '汽油'



    return result





'''
img = cv2.imread('sample\gas1.png') # 讀取圖像
gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) # 灰階處理 

max_val = np.max(gray_img) # 最大灰階值
min_val = np.min(gray_img) # 最小灰階值
threshold = (min_val + max_val) / 2  # 中間值
print(max_val,min_val,threshold)
for i in range(222):
    for j in range(426):
        if gray_img[i][j] >=  170:
            gray_img[i][j] = 255
        else:
            gray_img[i][j] = 0

cv2.imwrite('gas1_gray_example.png', gray_img) # 儲存圖像
'''


'''
img = cv2.imread('sample\gas2.png') # 讀取圖像

gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) # 灰階處理 

binary_adaptive_img = cv2.adaptiveThreshold(
    gray_img, 
    255, 
    cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
    cv2.THRESH_BINARY, 
    11,  # 區塊大小：必須是奇數，數字越大，處理的範圍越大，通常從11或15開始試
    2    # C值：從區塊平均值減去的數值，可以用來微調
)

cv2.imwrite('gas2_gray_example.png', binary_adaptive_img) # 儲存圖像
'''