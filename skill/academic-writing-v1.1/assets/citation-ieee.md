# IEEE 引用格式速查

> 依据：*IEEE Reference Guide*（IEEE 官方）；适用：电气、电子、计算机、通信、机械、土木等工程学科，以及绝大多数 IEEE 会议与期刊。
> 核心特征：**顺序编码制**——正文用方括号数字，按**首次出现顺序**编号，文末按同一顺序排列（不是字母序）。

## 1. 文内引用

| 场景 | 写法 |
|---|---|
| 单篇 | `[1]` |
| 多篇并列 | `[1], [3], [7]`（各自独立方括号） |
| 连续区间 | `[2]–[5]`（用 en dash） |
| 作为句子成分 | `as shown in [4]`（不写 "in reference [4]"） |
| 重复引用同一文献 | **沿用原编号**，不重新编号 |

**最常见的错误**：插入/删除文献后忘记全文重编号。IEEE 编号依赖出现顺序，任何顺序变动都会连锁改号——改稿后必须重排。

## 2. 期刊论文

```
A. B. Author and C. D. Author, "Title of paper," Abbrev. Journal Title, vol. 12, no. 3, pp. 45–67, May 2023, doi: 10.1109/XXX.2023.1234567.
```

要点：
- 作者名**缩写在前、姓在后**（`M. K. Sen`），与 APA 相反
- 作者超过 **6 位**用 `et al.`
- 文章题名加双引号，仅首词与专有名词大写
- 期刊名用**官方缩写**并斜体（`IEEE Trans. Antennas Propag.`）
- 卷 `vol.`、期 `no.`、页 `pp.`
- 月份用缩写：Jan., Feb., Mar., Apr., May, Jun., Jul., Aug., Sep., Oct., Nov., Dec.
- DOI 写作 `doi: 10.xxxx/xxxx`，**不加 `https://doi.org/`**

## 3. 会议论文

```
A. Author, "Title of paper," in Proc. Conf. Name, City, Country, 2023, pp. 45–67, doi: 10.1109/XXX.2023.1234567.
```

要点：用 `in Proc.` 引出会议录；会议地点与年份不可省。

## 4. 专著

```
A. Author, Title of Book, 2nd ed. City, Country: Publisher, 2023, pp. 45–67.
```

要点：书名斜体、**不加引号**；版次在书名后；出版地: 出版者, 年份。

## 5. 书的章节

```
A. Author, "Title of chapter," in Title of Book, B. Editor, Ed. City: Publisher, 2023, pp. 45–67.
```

## 6. 学位论文

```
A. Author, "Title of dissertation," Ph.D. dissertation, Dept. Name, Univ. Name, City, Country, 2023.
```

要点：必须标明学位类型（Ph.D. dissertation / M.S. thesis）与授予单位。

## 7. 标准

```
Title of Standard, Standard No. 1234-2023, 2023.
```

## 8. 预印本（arXiv）

```
A. Author, "Title of paper," arXiv:2301.12345, 2023.
```

## 9. 网页

```
A. Author, "Page title," Site Name. [Online]. Available: https://example.com. Accessed: Mar. 5, 2023.
```

## 10. 专利

```
A. Inventor, "Title of patent," U.S. Patent 1234567, 2023.
```

## 11. 十条自查

- [ ] 编号是否严格按首次出现顺序，且改稿后已重排
- [ ] 作者是否"缩写在前、姓在后"
- [ ] 作者超 6 位是否用 et al.
- [ ] 文章题名是否加引号，书名是否未加引号
- [ ] 期刊名是否用了官方缩写
- [ ] vol./no./pp. 是否齐全，页码范围是否用 en dash
- [ ] 月份是否用三字母缩写
- [ ] DOI 是否写成 `doi: 10.xxxx`（无 https）
- [ ] 文内编号与文末条目是否一一对应、数量一致
- [ ] 是否全文只用 IEEE 一套体系（不混 APA/Chicago）

> 期刊缩写查 IEEE 官方 *Abbreviations and Acronyms* 表；找不到时写全称，不要自造缩写。
