# 数字分心与同伴影响：移动应用使用对学术和劳动市场结果的影响

**Authors**: Panle Jia Barwick, Siyu Chen, Chao Fu, Teng Li
**Journal**: Quarterly Journal of Economics
**Year**: 2024

## 1. 总体信息提取
### 研究背景
随着对手机过度使用的担忧日益增加，尤其是在青少年和年轻人中，本研究提供了首个关于个人及同伴移动应用使用对学术表现、身体健康和劳动市场结果影响的综合证据。研究利用中国一所大学的行政数据和手机记录，通过随机室友分配和政策冲击，探讨了个人及同伴的移动应用使用对学术成绩、身体健康和劳动市场结果的影响。

### 研究意义
本研究不仅在理论上增进了对数字分心和同伴效应的理解，而且在实践上为制定相关政策提供了依据，如限制青少年手机使用时间的政策可能会对他们未来的劳动市场结果产生积极影响。

### 研究思路
研究首先通过随机室友分配来估计同伴效应，然后利用政策变化作为工具变量来分离行为溢出效应和情境同伴效应，最后探讨了移动应用使用对学术成绩和劳动市场结果的影响。

### 研究方法
研究者首先利用随机室友分配来估计同伴效应，然后通过政策变化作为工具变量来分离行为溢出效应和情境同伴效应。接着，研究者分析了个人及同伴的移动应用使用对学术成绩和劳动市场结果的影响，并探讨了这些影响的异质性。最后，研究者利用高频GPS数据和在线调查数据来探讨这些影响背后的机制。

### 研究结论
['移动应用使用具有传染性，室友的移动应用使用增加会导致个人使用增加。', '高移动应用使用对所有测量结果都是有害的，包括GPA和工资。', '室友的移动应用使用对个人的GPA和工资有直接和间接效应。', '限制未成年人游戏时间的政策可以提高大学生的初始工资。', '高频GPS数据显示，高应用使用挤出了学习时间和增加了迟到及缺课。']

## 2. 具体学术要素提取
### 变量信息
- **关键被解释变量**: 学术成绩（GPA）、劳动市场结果（工资）
- **解释变量**: 个人及室友的移动应用使用时间
- **机制变量**: 时间分配（学习时间、迟到和缺课）
- **工具变量**: 未成年人游戏限制政策、爆款游戏“原神”发布时间
- **控制变量**: 年龄、农村居住、高中理科/文科轨迹、大学入学考试成绩、房价（家庭财富代理变量）

## 3. 数据与方法
### 变量测算
通过手机记录测量移动应用使用时间，通过行政记录测量学术成绩和劳动市场结果。

### 数据来源
中国一所大学的行政记录和手机使用数据，以及通过GPS系统和在线调查收集的补充数据。

### 相关参考文献
- Abdulkadiroğlu, Atila, Joshua Angrist, and Parag Pathak, “The elite illusion: Achievement effects at Boston and New York exam schools,” Econometrica, 2014.
- Allcott, Hunt, Luca Braghieri, Sarah Eichmeyer, and Matthew Gentzkow, “The welfare effects of social media,” American Economic Review, 2020.
- Brock, William A and Steven N Durlauf, “A multinomial choice model with social interactions,” in “The Economy as an Evolving Complex System III,” Oxford University Press, New York, 2006.
- Sacerdote, Bruce, “Peer effects with random assignment: Results for Dartmouth roommates,” The Quarterly Journal of Economics, 2001.

## 4. Stata 代码建议
```stata
* 以二元游戏限制政策作为工具变量的2SLS回归
ivregress 2sls y x (z = iv), first
* 以爆款游戏发布作为工具变量的2SLS回归
ivregress 2sls y x (z = iv), first
```
