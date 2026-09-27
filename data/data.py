import numpy as np
import matplotlib.pyplot as plt

x = np.linspace(-5, 10, 500)
times = [0, 1, 2, 3]

plt.figure(figsize=(8, 4))
for t in times:
    u = np.exp(-(x - t)**2)
    plt.plot(x, u, label=f't = {t}')

plt.xlabel('x')
plt.ylabel('u(x,t)')
plt.title('输运方程 u_t + u_x = 0 的解：波形向右平移')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.6)
plt.show()