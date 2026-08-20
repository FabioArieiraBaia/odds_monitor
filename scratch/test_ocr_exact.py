import cv2
import numpy as np

# Test matching single digits
canvas = np.zeros((36, 24), dtype=np.uint8)
cv2.putText(canvas, "7", (3, 27), cv2.FONT_HERSHEY_DUPLEX, 0.7, 255, 1)

template = np.zeros((36, 24), dtype=np.uint8)
cv2.putText(template, "7", (3, 27), cv2.FONT_HERSHEY_DUPLEX, 0.7, 255, 1)

res = cv2.matchTemplate(canvas, template, cv2.TM_CCOEFF_NORMED)
print("Score matching 7 to 7:", res[0][0])
