import sys
print(sys.version)
import matplotlib.pyplot as plt
x = [0, 20, 40, 60, 80, 100]
y = ["Submitted", "Received", "Verified", "Work Started", "Almost Done", "Solved"]
plt.plot(x, y)
plt.show()
