import paddle
from paddleocr import PaddleOCR
from rapidfuzz import fuzz
from opencc import OpenCC
import re
import math
import os
import re
import cv2
import numpy as np


ocr = PaddleOCR(use_textline_orientation=True, lang='ch')

def ocr_recognize(file_location):

    answer = {"用電度數":"", "期間起日":"", "期間迄日":"", "備註":"辨識成功"}

    # 初始化快速 OCR 模型（mobile 版本 PP-OCRv4），只用於快速定位文字位置
    '''ocr = PaddleOCR(
         lang='ch',                              # 設定語言為中文
         ocr_version='PP-OCRv4',                # 使用 PP-OCRv4 模型
        use_doc_orientation_classify=False,     # 不偵測文件旋轉角度，快速但需保證圖片方向正確
        use_doc_unwarping=False                 # 不做透視校正（去除傾斜），加快速度
    )'''
    
    #ocr = PaddleOCR(use_textline_orientation=True, lang='ch')

    # 啟動 OCR辨識
    result = ocr.predict(file_location)  

    print(f"是否使用 GPU: {paddle.is_compiled_with_cuda()}")
    print(f"當前設備: {paddle.get_device()}")

    # 辨識後所需的資訊，包含:文字, 信心度, 座標
    ocr_result = result[0]  

    rec_texts = ocr_result['rec_texts']     # 文字
    rec_scores = ocr_result['rec_scores']   # 信心度
    rec_polys = ocr_result['rec_polys']     # 座標

    # print(ocr_result)

    # ========== 初始化信心度變數 ==========
    score = 0
    date_score = 0

    polys = None
    target = "計費度數（度）/EnergyConsumption(kWh)"
    for text, poly in zip(rec_texts,rec_polys):

        # 找到 "計費度數" 的座標，但因辨識結果可能會漏字，利用模糊匹配找到相似度最高的，且字串長度設定需大於15
        similarity = fuzz.partial_ratio(target, str(text))

        if similarity > 80 and len(text) > 15 :  # 閥值可根據測試調整
            polys = poly
            #print(f"成功匹配！相似度：{similarity}%")
            #print(f"文字:{text}, 座標:{poly}")

    if polys is None:
        print("辨識失敗，找不到用電度數")
    else:

        # 計算 "計費度數" 的中心座標
        sum_x = sum(point[0] for point in polys)
        sum_y = sum(point[1] for point in polys)
            
        center_x = int(sum_x // 4)
        center_y = int(sum_y // 4)
            
        N_center = [center_x, center_y]  # "計費度數" 的中心座標

        # 篩選出字串中有數字的結果，並將該字串左上角的座標儲存
        Used_text = [] # 包含數字之字串的內容
        Used_poly = [] # 包含數字之字串的中心座標
        Used_score = []
        for text, poly, scores in zip(rec_texts,rec_polys,rec_scores):
            
            
            if re.search(r"\d", text):

                sum_x = sum(point[0] for point in poly)
                sum_y = sum(point[1] for point in poly)
                
                center_x = int(sum_x // 4)
                center_y = int(sum_y // 4)
                
                Used_poly = Used_poly + [[center_x, center_y]]
                Used_text = Used_text + [text]
                Used_score = Used_score + [scores]

        #print(Used_text)
        # print(Used_poly)


        # 計算 "計費度數" 以下的字串與 "計費度數" 的距離，找到距離最近的字串即為用電度數
        min_distance = 100000
        Used = ""
        score = 0
        for text, poly, scores in zip(Used_text, Used_poly, Used_score):

            if poly[1] > N_center[1]:   # 只考慮 "計費度數" 以下的字串

                distance = math.dist(N_center, poly) # 計算 "計費度數" 的中心座標與該字串的中心座標之間的距離

                if distance < min_distance and len(re.sub(r'\d', '', text)) < 5:
                    Used = text
                    score = scores
                    min_distance = distance
        answer["用電度數"] = re.sub(r'\D', '', Used)
        print(f"用電度數:{Used}")
        print(f"用電度數信心度:{score}")









    cc = OpenCC('s2t')  # Simplified -> Traditional

    # 找到計費期間字串的座標位置
    target1 = "計"
    target2 = "費"
    target3 = "期"
    target4 = "間"
    date_poly = None
    date_text = ""
    date_score = 0
    total_similarity = 0
    # 計算每個字串與 "計費期間" 的相似度，找到相似度最高的字串，即為 "計費期間" 的位置
    for text, poly, scores in zip(rec_texts, rec_polys, rec_scores):

        similarity1 = fuzz.partial_ratio(target1, cc.convert(str(text))) 
        similarity2 = fuzz.partial_ratio(target2, cc.convert(str(text)))
        similarity3 = fuzz.partial_ratio(target3, cc.convert(str(text))) 
        similarity4 = fuzz.partial_ratio(target4, cc.convert(str(text)))
        total = similarity1 + similarity2 + similarity3 + similarity4
    

        if total > total_similarity:
            total_similarity = total
            date_poly = poly
            date_text = text
            date_score = scores
            #print(f"成功匹配！相似度：{total_similarity}%")
            #print(f"文字:{text}, 座標:{poly}, 信心度:{scores}")

    pattern = r'\d{3}[\/.-]\d{2}[\/.-]\d{2}'
    dates = []  # ← 先初始化 dates
    
    # 判斷是否有找到 "計費期間"，沒有則輸出錯誤
    if date_poly is None:
        print("辨識失敗，找不到計費期間")

    # 先篩選計算期間的字串是否已經包含日期資訊，利用正規表達式找 --> yyy/mm/dd, yyy-mm-dd, yyy.mm.dd 等格式的日期
    elif re.search(pattern, date_text):
        dates = re.findall(pattern ,date_text)
        print(f"期間起日:{dates[0]}, 期間迄日:{dates[1]}")
        print(f"計費期間信心度:{date_score}")

    # 如果 "計費期間" 的字串中沒有日期資訊，則在 "計費期間" 的上下邊界之間尋找包含日期資訊的字串
    else:

        up_y = date_poly[0][1]    # 上邊界
        down_y = date_poly[3][1]  # 下邊界


        # 計算 "計費期間" 的中心座標
        sum_x = sum(point[0] for point in date_poly)
        sum_y = sum(point[1] for point in date_poly)
            
        center_x = int(sum_x // 4)
        center_y = int(sum_y // 4)

        center = [center_x, center_y]

        
        pattern = r'\d{3}[\/.-]\d{2}[\/.-]\d{2}'
        min_y_distance = 100000
        date_text = ""
        date_score = 0
        for text, poly, scores in zip(rec_texts, rec_polys, rec_scores):

            sum_x = sum(point[0] for point in poly)
            sum_y = sum(point[1] for point in poly)
                
            # 使用 // 進行整除，因為像素座標通常是整數
            center_x = int(sum_x // 4)
            center_y = int(sum_y // 4)

            if re.search(pattern, text) and (up_y) <= center_y <= (down_y):
                if abs(center_y - center[1]) < min_y_distance:
                    min_y_distance = abs(center_y - center[1])
                    date_text = text
                    date_score = scores
                    print(text)

        dates = re.findall(pattern, date_text)


    if dates != []:
        if len(dates) < 2:
            print("辨識失敗，找不到完整的計費期間日期資訊")
        else:
            answer["期間起日"] = dates[0]
            answer["期間迄日"] = dates[1]
            print(f"期間起日:{dates[0]}, 期間迄日:{dates[1]}")
            print(f"計費期間信心度:{date_score}")
    else:
        
        
        up_y = date_poly[0][1]    # 上邊界
        right_x = date_poly[1][0] # 右邊界
        left_x = date_poly[0][0]  # 左邊界
        for text, poly, scores in zip(rec_texts, rec_polys, rec_scores):
            if re.search(pattern, text):

                sum_x = sum(point[0] for point in poly)
                sum_y = sum(point[1] for point in poly)
                
                center_x = int(sum_x // 4)
                center_y = int(sum_y // 4)

                if left_x <= center_x <= right_x and center_y >= up_y:
                    date = text
                    date = re.findall(pattern, date)
                    print(date)
                    print(f"信心度:{scores}")
                    dates.append(date)
                        
    if len(dates) < 2:
        print("辨識失敗，找不到完整的計費期間日期資訊")
    else:
        answer["期間起日"] = dates[0]
        answer["期間迄日"] = dates[1]          
        print(f"期間起日:{dates[0]}, 期間迄日:{dates[1]}")

    # ==================== 修改區塊：信心度分級 + 換行 ====================
    
    usage_value = answer["用電度數"]
    date_start = answer["期間起日"]
    date_end = answer["期間迄日"]
    
    # 用電度數狀態判斷
    if usage_value == "" or score < 0.5:
        usage_status = "failed"
    elif 0.5 <= score <= 0.7:
        usage_status = "low"
    else:
        usage_status = "success"
    
    # 計費期間狀態判斷
    if date_start == "" or date_end == "" or date_score < 0.5:
        date_status = "failed"
    elif 0.5 <= date_score <= 0.7:
        date_status = "low"
    else:
        date_status = "success"
    
    # 9 種組合判斷（只有全成功顯示「辨識成功」，其他只顯示提醒）
    if usage_status == "success" and date_status == "success":
        answer["備註"] = "辨識成功"
    elif usage_status == "success" and date_status == "low":
        answer["備註"] = "期間信心度偏低"
    elif usage_status == "success" and date_status == "failed":
        answer["備註"] = "計費期間辨識失敗"
    elif usage_status == "low" and date_status == "success":
        answer["備註"] = "用電信心度偏低"
    elif usage_status == "low" and date_status == "low":
        answer["備註"] = "信心度偏低"
    elif usage_status == "low" and date_status == "failed":
        answer["備註"] = "計費期間辨識失敗\n用電信心度偏低"
    elif usage_status == "failed" and date_status == "success":
        answer["備註"] = "用電度數辨識失敗"
    elif usage_status == "failed" and date_status == "low":
        answer["備註"] = "用電度數辨識失敗\n期間信心度偏低"
    elif usage_status == "failed" and date_status == "failed":
        answer["備註"] = "辨識失敗"
    
    # ==================== 修改區塊結束 ====================
    
    print(f"用電狀態:{usage_status}, 日期狀態:{date_status}")
    print(f"最終備註:{answer['備註']}")
            
    return answer

ocr_recognize("uploads\IMG_2525.JPG")