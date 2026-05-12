'''
import time
from paddleocr import PaddleOCR

start_total = time.time()

ocr = PaddleOCR(use_angle_cls=True, lang='ch')

start_ocr = time.time()
result = ocr.ocr('Image\IMG_2524.JPG')
end_ocr = time.time()

end_total = time.time()

print("OCR時間:", end_ocr - start_ocr)
print("總時間:", end_total - start_total) '''




"""
from paddleocr import PaddleOCR
import cv2

# 讀圖片
img_path = "Image\IMG_2525.JPG"
img = cv2.imread(img_path)

# 裁切一小塊（確保有文字）
h, w, _ = img.shape
crop = img[int(h*0.3):int(h*0.5), int(w*0.3):int(w*0.7)]

cv2.imwrite("crop_test.jpg", crop)

# 初始化（v5 正確寫法）
ocr = PaddleOCR(lang='ch')  # ❗不要加 rec / det

# ❗ 直接用 predict（新版）
result = ocr.predict("crop_test.jpg")

print("辨識結果：")
for line in result:
    print(line)

"""

# 速度還行,精度高
'''
from paddleocr import PaddleOCR
import time

image_path = "crop_test.jpg"

ocr = PaddleOCR(
    lang='ch',
    use_doc_orientation_classify=False,  # 關掉加速
    use_doc_unwarping=False              # 關掉加速
)

start = time.time()
result = ocr.predict(image_path)
end = time.time()

print(f"OCR時間: {end - start:.2f} 秒")

# 印結果
for text in result[0]['rec_texts']:
    print(text)
'''

# 速度很快，精度高
'''
from paddleocr import PaddleOCR
import time

image_path = "crop_test.jpg"

ocr = PaddleOCR(
    lang='ch',

    # ❗強制使用 mobile（重點）
    ocr_version='PP-OCRv4',

    # 🚀 關閉不必要模組
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False
)

start = time.time()
result = ocr.predict(image_path)
end = time.time()

print(f"OCR時間: {end - start:.2f} 秒")

for text in result[0]['rec_texts']:
    print(text)
'''

import re

import numpy as np

from paddleocr import PaddleOCR  # 引入 PaddleOCR 類別，負責文字檢測與辨識
import cv2                        # 引入 OpenCV，用於圖片讀取、裁切、存檔等影像操作
from opencc import OpenCC          # opencc 用於簡體 ↔ 繁體轉換

def ocr_recognize(file_location):

    final_result = {"計費期間":"", "用電度數":""}
    FinalResult = {"期間起日":" ", "期間迄日":" ", "收據月份":" ","用電度數":" "}

    cc = OpenCC('s2t')  # s2t = simplified to traditional

    # 定義要辨識的圖片路徑
    #image_path = "Image\IMG_2525.JPG"
    
    # 讀取整張圖片
    img = cv2.imread(file_location)

    # 初始化快速 OCR 模型（mobile 版本 PP-OCRv4），只用於快速定位文字位置
    ocr_fast = PaddleOCR(
        lang='ch',                              # 設定語言為中文
        ocr_version='PP-OCRv4',                 # 使用 PP-OCRv4 模型
        use_doc_orientation_classify=False,     # 不偵測文件旋轉角度，快速但需保證圖片方向正確
        use_doc_unwarping=False                 # 不做透視校正（去除傾斜），加快速度
    )

    # 對整張圖片做快速 OCR，取得文字與邊界框結果
    # predict 會回傳每頁結果的 list，單張圖片取 [0]
    result = ocr_fast.predict(file_location)[0]



    # 遍歷快速 OCR 辨識出的文字與其對應邊界框
    for text, box in zip(result['rec_texts'], result['rec_polys']):
        

        text = cc.convert(text) # 轉繁體中文

        if "Energy" in text :

            #print("座標位置:")
            #for point in box:
            #  print(point)

            # 將多邊形座標轉成矩形邊界框 (x_min, y_min, x_max, y_max)
            x_min = min(p[0] for p in box)
            y_min = min(p[1] for p in box)
            x_max = max(p[0] for p in box)
            y_max = max(p[1] for p in box)

            # 放大 ROI，避免裁切太緊導致文字缺失
            roi = img[y_min-50:y_max+50, x_min-10:x_max+300]


            # 將裁切的區域存成檔案，供高精度 OCR 使用
            cv2.imwrite("roi_kWh.jpg", roi)

            
            
            ocr_precise = PaddleOCR(
                lang='ch',                  # 中文
                ocr_version='PP-OCRv5',     # 使用最新精準 server 模型
                use_angle_cls=True,          # 啟用文字旋轉偵測
                use_doc_orientation_classify=True,  # 文件方向校正
                use_doc_unwarping=True       # 文件透視校正
            )


            # 對裁切後的小區域圖片做 OCR
            roi_result = ocr_precise.predict("roi_kWh.jpg")

            # 印出精準辨識結果
            #print("精準辨識:")
            #print(roi_result[0]['rec_texts'])

            pattern = r".*數$"
            index = 0
            for texts in roi_result[0]['rec_texts']:

                texts = cc.convert(texts) # 轉繁體中文
                print(texts)
                if re.search(pattern, texts, re.DOTALL):
                    break
                index += 1
            #print(index)
            print("用電度數:", roi_result[0]['rec_texts'][index+1])
            final_result["用電度數"] = roi_result[0]['rec_texts'][index+1]



        elif "計費期間" in text :
            #print("找到關鍵字:", text)  # 印出找到的文字（方便確認）
            #print("座標位置:")
            #for point in box:
            #   print(point)

            
            x_min = min(p[0] for p in box)
            y_min = min(p[1] for p in box)
            x_max = max(p[0] for p in box)
            y_max = max(p[1] for p in box)

            # 放大 ROI，避免裁切太緊導致文字缺失
            roi = img[y_min-50:y_max+50, x_min-10:x_max+300]


            # 將裁切的區域存成檔案，供高精度 OCR 使用
            cv2.imwrite("roi_date.jpg", roi)

            
            
            ocr_precise = PaddleOCR(
                lang='ch',                  # 中文
                ocr_version='PP-OCRv5',     # 使用最新精準 server 模型
                use_angle_cls=True,          # 啟用文字旋轉偵測
                use_doc_orientation_classify=True,  # 文件方向校正
                use_doc_unwarping=True       # 文件透視校正
            )


            # 對裁切後的小區域圖片做 OCR
            roi_result = ocr_precise.predict("roi_date.jpg")

            # 印出精準辨識結果
            #print("精準辨識:")
            #print(roi_result[0]['rec_texts'])

            index = 0
            for texts in roi_result[0]['rec_texts']:

                texts = cc.convert(texts) # 轉繁體中文
                
                if "計費期間" in texts:
                    break
                index += 1

            #print(index)
            #print("計費期間:", roi_result[0]['rec_texts'][index+1])
            final_result["計費期間"] = roi_result[0]['rec_texts'][index+1]

    # 民國年 → 西元年
    def minguo_to_ad(date_str):
        year, month, day = map(int, date_str.split('/'))
        year += 1911
        return f"{year}/{month:02d}/{day:02d}"  # 格式化成 YYYY/MM/DD

    # 拆開起訖日期
    start_minguo, end_minguo = final_result['計費期間'].split('至')
    start_ad = minguo_to_ad(start_minguo)
    end_ad = minguo_to_ad(end_minguo)

    # 將結果整理成列表，對應表格欄位
    table_row = [start_ad, end_ad, final_result['用電度數']]

    FinalResult["收據月份"] = table_row[0][:7]
    FinalResult["期間起日"] = table_row[0]
    FinalResult["期間迄日"] = table_row[1]
    FinalResult["用電度數"] = table_row[2]

    return FinalResult

#print(ocr_recognize("IMG_2524.JPG"))