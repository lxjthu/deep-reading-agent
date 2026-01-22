# 数字分心与同伴影响：移动应用使用对学术和劳动市场结果的影响

**Authors**: Panle Jia Barwick, Siyu Chen, Chao Fu, Teng Li
**Journal**: 未提供
**Year**: 未提供

## 1. 总体信息提取
### 研究背景
随着移动电话的过度使用，尤其是青少年和年轻人，全球范围内的担忧不断增加。本文提供了首个关于个人和同伴移动应用使用如何影响学术表现、身体健康和劳动市场结果的全面证据。研究利用中国一所大学的行政数据和手机记录，通过随机室友分配和政策冲击，探讨了个人和同伴手机应用使用的影响。研究发现，高应用使用对所有衡量结果都有负面影响，室友的应用使用通过直接和间接效应对GPA和工资产生负面影响。

### 研究意义
本研究不仅理论上拓展了对数字成瘾的理解，而且在实践上为制定减少移动应用过度使用的干预政策提供了依据。

### 研究思路
研究首先通过随机室友分配来估计同伴效应，然后利用政策变化作为工具变量来分离行为溢出效应和情境同伴效应，最后探讨了这些效应对学术表现和劳动市场结果的影响。

### 研究方法
研究使用了工具变量方法，包括未成年人游戏限制政策和爆款游戏“原神”发布日期作为工具变量，来估计移动应用使用对学术表现和劳动市场结果的影响。

### 研究结论
['移动应用使用具有传染性，室友的应用使用增加会导致个人应用使用增加。', '高应用使用对学术表现和劳动市场结果有负面影响。', '室友的应用使用通过直接和间接效应对个人的GPA和工资产生负面影响。', '限制未成年人游戏时间的政策可以提高大学生的初始工资。', '应用使用通过时间分配影响学术表现，高应用使用导致学生在图书馆的时间减少，迟到和缺课增加。']

## 2. 具体学术要素提取
### 变量信息
- **关键被解释变量**: 学术表现（GPA）、劳动市场结果（工资）
- **解释变量**: 个人和室友的移动应用使用时间
- **机制变量**: 时间分配（图书馆时间、宿舍时间）、迟到和缺课
- **工具变量**: 未成年人游戏限制政策、爆款游戏“原神”发布日期
- **控制变量**: 年龄、农村居住、高中理科/文科轨迹、大学入学考试成绩、房价（家庭财富代理）

## 3. 数据与方法
### 变量测算
移动应用使用时间通过手机记录的月度使用时间来衡量，GPA和工资通过学校行政记录来衡量。

### 数据来源
中国一所大学的行政记录和手机使用数据，以及通过手机GPS系统收集的地理位置数据和在线调查。

### 相关参考文献
- Abdulkadiroğlu, Atila, Joshua Angrist, and Parag Pathak, “The elite illusion: Achievement effects at Boston and New York exam schools,” Econometrica, 2014, 82 (1), 137–196.
- Allcott, Hunt, Luca Braghieri, Sarah Eichmeyer, and Matthew Gentzkow, “The welfare effects of social media,” American Economic Review, 2020, 110 (3), 629–676.
- Brock, William A and Steven N Durlauf, “A multinomial choice model with social interactions,” in “In: Blume, L., Durlauf, S. (Eds.), The Economy as an Evolving Complex System III,” Oxford University Press, New York, 2006.
- Sacerdote, Bruce, “Peer effects with random assignment: Results for Dartmouth roommates,” The Quarterly Journal of Economics, 2001, 116 (2), 681–704.

## 4. Stata 代码建议
```stata
* 工具变量估计
ivregress 2sls y x (z = w1 w2)

* 随机效应模型
xtreg y x, fe

* 固定效应模型
xtreg y x, re

* 动态面板数据模型
xtabond y L.y x, gmm(L.y, lag(2 3))

* 事件研究
gen timevar = _n
reg y i.timevar##i.post
```
