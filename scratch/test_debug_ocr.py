import cv2
import numpy as np

# Create template for digit 1
tmpl = np.zeros((28, 18), dtype=np.uint8)
cv2.putText(tmpl, "1", (2, 22), cv2.FONT_HERSHEY_DUPLEX, 0.65, 255, 1)

# Sample digit 1 crop
img = np.zeros((50, 140, 3), dtype=np.uint8)
img[:] = (24, 28, 36)
cv2.putText(img, "1", (18, 20), cv2.FONT_HERSHEY_DUPLEX, 0.65, (200, 200, 200), 1)

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, binary = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY)
contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
x, y, w, h = cv2.boundingRect(contours[0])
crop = binary[y:y+h, x:x+w]

# Pad to maintain aspect ratio
max_dim = max(w, h)
padded = np.zeros((max_dim + 4, max_dim + 4), dtype=np.uint8)
y_off = (max_dim + 4 - h) // 2
x_off = (max_dim + 4 - w) // 2
padded[y_off:y_off+h, x_off:x_off+w] = crop
resized = cv2.resize(padded, (18, 28))

res = cv2.matchTemplate(resized, tmpl, cv2.TM_CCOEFF_NORMED)
print("Score with aspect padding:", res[0][0])
