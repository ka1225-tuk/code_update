import matplotlib.pyplot as plt
import matplotlib.patches as patches

# ──────────────────────────────
# 가로형 신호등 클래스
# ──────────────────────────────
class TrafficLight:
    def __init__(self, ax):
        # 신호등 박스 (가로형)
        self.box = patches.Rectangle((0, 0), 3, 1, linewidth=2,
                                     edgecolor='black', facecolor='black')
        ax.add_patch(self.box)

        # 원 3개 (왼쪽=빨강, 가운데=노랑, 오른쪽=초록)
        self.red = patches.Circle((0.5, 0.5), 0.4, color='dimgray')
        self.yellow = patches.Circle((1.5, 0.5), 0.4, color='dimgray')
        self.green = patches.Circle((2.5, 0.5), 0.4, color='dimgray')

        ax.add_patch(self.red)
        ax.add_patch(self.yellow)
        ax.add_patch(self.green)

        ax.set_xlim(-0.5, 3.5)
        ax.set_ylim(-0.5, 1.5)
        ax.axis('off')

    def set_light(self, color):
        # 모두 꺼짐 (회색)
        self.red.set_color('dimgray')
        self.yellow.set_color('dimgray')
        self.green.set_color('dimgray')

        if color == 'red':
            self.red.set_color('red')
        elif color == 'yellow':
            self.yellow.set_color('yellow')
        elif color == 'green':
            self.green.set_color('green')

        plt.draw()
        plt.pause(0.01)


# ──────────────────────────────
# 실행부
# ──────────────────────────────
fig, ax = plt.subplots(figsize=(18,6))
light = TrafficLight(ax)

while True:
    light.set_light('red')
    plt.pause(3)   # 빨강 3초

    light.set_light('green')
    plt.pause(20)   # 초록 3초

    #light.set_light('yellow')
    #plt.pause(1)   # 노랑 1초
