# PaddleOCR 模組
from paddleocr import PaddleOCR
import paddle

# 模糊匹配模組
from rapidfuzz import fuzz 

# 正規表達式模組
import re              

# 字體轉換模組
from opencc import OpenCC

# 圖片處理模組
import cv2

# 其他模組
import numpy as np
import math
import os

# 定義一個函數來檢查字串是否為純數字
def is_numeric(text):
    try:
        float(text)
        return True
    except ValueError:
        return False
    
# 簡體 轉 繁體
cc = OpenCC('s2t')  

# 初始化 OCR模型
ocr = PaddleOCR(use_textline_orientation=True, lang='ch')


def gas_recognize(file_location):

    answer = {"日期":"", "油品":"", "用量":"", "備註":"辨識成功"}

    # 啟動 OCR 模型進行辨識
    result = ocr.predict(file_location)  

    # 取得辨識結果，包含文字、信心度和座標
    ocr_result = result[0] 

    rec_texts = ocr_result['rec_texts']     # 文字
    rec_scores = ocr_result['rec_scores']   # 信心度
    rec_polys = ocr_result['rec_polys']     # 座標

    print("===============================================")
    print(f"收據: {file_location}") 

    
    target1 = "品"
    target2 = "名"
    target3 = "數"
    target4 = "量"
    date_score = 0
    target_text = None
    target_poly = None
    target_score = None
    score = 0

    # 找到 日期 與 "品名/數量"座標
    for text, poly, scores in zip(rec_texts, rec_polys, rec_scores):

        if answer["日期"] == "":
            date = re.search(r'\d{4}-\d{2}-\d{2}', text)
            if date:
                answer["日期"] = date.group()
                date_score = scores
       
        similarity1 = fuzz.partial_ratio(target1, cc.convert(str(text)))
        similarity2 = fuzz.partial_ratio(target2, cc.convert(str(text)))
        similarity3 = fuzz.partial_ratio(target3, cc.convert(str(text)))
        similarity4 = fuzz.partial_ratio(target4, cc.convert(str(text)))
        total_similarity = similarity1 + similarity2 + similarity3 + similarity4

        if total_similarity > 200 and total_similarity > score:
            score = total_similarity
            target_text = text
            target_poly = poly
            target_score = scores 

    if target_poly is None:
        #print("找不到品名/數量，辨識失敗")
        answer["備註"] = "辨識失敗"
        return answer
    print(f"日期:{answer['日期']}")
    print(f"日期信心度:{date_score}")


    # 計算 "品名/數量" 的中心座標
    sum_x = sum(point[0] for point in target_poly)
    sum_y = sum(point[1] for point in target_poly)
    center_x = int(sum_x // 4)
    center_y = int(sum_y // 4)
    center = [center_x, center_y]


    texts = None
    polys = None
    score = None
    min_distance = 100000

    # 找出油品種類並記錄其座標
    for text, poly, scores in zip(rec_texts, rec_polys, rec_scores):

        sum_x = sum(point[0] for point in poly)
        sum_y = sum(point[1] for point in poly)
            
        center_x = int(sum_x // 4)
        center_y = int(sum_y // 4)
            
        if center_y > center[1]:

            distance = math.dist(center, [center_x, center_y]) 

            if distance < min_distance:
                min_distance = distance
                texts = cc.convert(str(text))
                polys = poly
                score = scores

    print(f"油品:{texts}")
    print(f"油品信心度:{score}")
    
    # 油品校正
    oil_failed = False
    if re.search(r"\d", texts):
        if "2" in texts:
            texts = "車用汽油"
        elif "5" in texts:
            texts = "車用汽油"          
        elif "8" in texts:
            texts = "車用汽油"
        else:
            texts = ""
            oil_failed = True
    else:
        if "二" in texts:
            texts = "車用汽油"
        elif "五" in texts:
            texts = "車用汽油"
        elif "八" in texts:
            texts = "車用汽油"
        elif "柴" in texts or "油" in texts:
            texts = "柴油"
        else:
            texts = ""
            oil_failed = True

    answer["油品"] = texts

    # 計算 "油品種類" 的中心座標
    sum_x = sum(point[0] for point in polys)
    sum_y = sum(point[1] for point in polys)      
    center_x = int(sum_x // 4)
    center_y = int(sum_y // 4)
    center = [center_x, center_y]


    
    n_texts = None
    n_polys = None
    n_scores = 0
    min_distance = 100000

    # 找出用量
    for text, poly, scores in zip(rec_texts, rec_polys, rec_scores):

            sum_x = sum(point[0] for point in poly)
            sum_y = sum(point[1] for point in poly)
            center_x = int(sum_x // 4)
            center_y = int(sum_y // 4)

            if center_y > center[1] and is_numeric(text):

                distance = math.dist(center, [center_x, center_y])

                if distance < min_distance:
                    min_distance = distance
                    n_texts = cc.convert(str(text))
                    n_polys = poly
                    n_scores = scores

    answer["用量"] = n_texts if n_texts else ""
    print(f"用量:{answer['用量']}")
    print(f"用量信心度:{n_scores}")


    # ==================== 信心度分級 + 備註判斷 ====================
    
    date_value = answer["日期"]
    usage_value = answer["用量"]
    
    # 日期狀態（日期為 "找不到日期資訊" 也算失敗）
    if date_value == "" or date_value == "找不到日期資訊" or date_score < 0.5:
        date_status = "failed"
    elif 0.5 <= date_score <= 0.7:
        date_status = "low"
    else:
        date_status = "success"
    
    # 用量狀態
    if usage_value == "" or n_scores < 0.5:
        usage_status = "failed"
    elif 0.5 <= n_scores <= 0.7:
        usage_status = "low"
    else:
        usage_status = "success"
    
    # 油品狀態
    oil_status = "failed" if oil_failed else "success"
    
    # 組合判斷
    if date_status == "success" and usage_status == "success" and oil_status == "success":
        answer["備註"] = "辨識成功"
    elif date_status == "failed" and usage_status == "failed" and oil_status == "failed":
        answer["備註"] = "辨識失敗"
    else:
        remarks = []
        if date_status == "failed":
            remarks.append("日期辨識失敗，請自行輸入")
        elif date_status == "low":
            remarks.append("日期信心度偏低")
        
        if usage_status == "failed":
            remarks.append("用量辨識失敗，請自行輸入")
        elif usage_status == "low":
            remarks.append("用量信心度偏低")
        
        if oil_status == "failed":
            remarks.append("油品辨識失敗")
        
        answer["備註"] = "\n".join(remarks)
    
    print(f"日期狀態:{date_status}, 用量狀態:{usage_status}, 油品狀態:{oil_status}")
    print(f"最終備註:{answer['備註']}")
    
    return answer