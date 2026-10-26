> Bản dịch tiếng Việt của [`docs/en/research/rainfall-insar-hazard.md`](../../en/research/rainfall-insar-hazard.md) (bản gốc tiếng Anh là bản chuẩn, ADR-015). Dịch ngày 2026-10-26, biên tập lại 2026-10-26.

# Mưa và InSAR trong phân vùng nguy cơ sụt lún và trượt lở

> Ghi chú nghiên cứu, đồng thời mô tả phương pháp của `geoeyes hazard` (gói `geoeyes.hazard`, trang **Phân tích chuyên đề** trên ứng dụng web).
> Trạng thái: **đã triển khai v1 ngày 2026-10-25**; kết quả đầu tiên trên các dự án thử nghiệm của GeoEyes nêu ở §7.
> Bản ghi quyết định: ADR-024 trong [`docs/vi/architecture/decisions.md`](../architecture/decisions.md).

## Mục lục

1. [Câu hỏi và phạm vi](#1-câu-hỏi-và-phạm-vi)
2. [Tổng quan tài liệu](#2-tổng-quan-tài-liệu)
3. [Giả thuyết](#3-giả-thuyết)
4. [Phương pháp (v1, đã triển khai)](#4-phương-pháp-v1-đã-triển-khai)
5. [Tham số và căn cứ chọn giá trị mặc định](#5-tham-số-và-căn-cứ-chọn-giá-trị-mặc-định)
6. [Trình tự nghiên cứu](#6-trình-tự-nghiên-cứu)
7. [Kết quả đầu tiên trên các dự án GeoEyes](#7-kết-quả-đầu-tiên-trên-các-dự-án-geoeyes)
8. [Hạn chế](#8-hạn-chế)
9. [Triển khai](#9-triển-khai)
10. [Tài liệu tham khảo](#10-tài-liệu-tham-khảo)

---

## 1. Câu hỏi và phạm vi

**Câu hỏi.** Liệu có thể kết hợp chuỗi thời gian chuyển dịch InSAR với lượng mưa để phân vùng nguy cơ chuyển dịch
mặt đất (sụt lún và trượt lở chậm) sao cho: (a) mỗi bước đều dựa trên phương pháp đã công bố, (b) chỉ rõ mưa bổ sung
được gì so với riêng InSAR, và (c) tái lập được trên mọi sản phẩm GeoEyes?

**Phạm vi của v1.**

- Đầu vào: một sản phẩm điểm của GeoEyes, gồm các điểm tán xạ bền vững (PS) và điểm tán xạ phân bố (DS), chuỗi
  chuyển dịch theo hướng nhìn của vệ tinh (LOS) và vectơ đơn vị LOS; một mô hình số độ cao (DEM); và lượng mưa dạng
  lưới, lấy từ CHIRPS v3, dự phòng bằng ERA5.
- Hai quá trình: **sụt lún** trên nền phẳng và **trượt lở chậm** trên sườn dốc. Cả hai đều diễn ra *chậm*, đúng dải
  tốc độ mà InSAR đo được (từ mm/năm đến vài dm/năm).
- Đầu ra: **mức nguy cơ** (từ rất thấp đến rất cao) cho từng ô phân tích. Đây là bản đồ *nguy cơ* hiểu theo nghĩa
  định tính, dựa trên ma trận, như cách dùng trong phương pháp giao thoa điểm tán xạ bền vững (PSI) của Cigna et al.
  (2013). Đây không phải nguy cơ xác suất theo nghĩa của Fell et al. (2008), vì v1 chưa ước tính chu kỳ lặp hay xác
  suất phá huỷ. Đây cũng không phải bản đồ *rủi ro*: mức độ phơi nhiễm và tính dễ tổn thương chưa thuộc phạm vi v1
  (§6, R6).

**Chưa thuộc phạm vi v1** (đã đưa vào trình tự nghiên cứu): mưa kích hoạt trượt lở nhanh ở quy mô sự kiện (ngưỡng
cường độ – thời đoạn, dự báo tức thời), mô hình thống kê tính nhạy cảm, tách chuyển dịch 3-D từ hai hình học chụp, và
hiệu chỉnh các lớp theo danh mục thiệt hại hoặc danh mục trượt lở.

## 2. Tổng quan tài liệu

### 2.1 Nguy cơ, tính nhạy cảm, phân vùng

- Khái niệm phân vùng nguy cơ và hệ thuật ngữ đi kèm có từ Varnes và Uỷ ban IAEG (1984). Bộ hướng dẫn JTC-1 của
  Fell et al. (2008) phân biệt rõ **tính nhạy cảm** (ở đâu), **nguy cơ** (ở đâu, bao lâu một lần, quy mô bao nhiêu)
  và **rủi ro** (xét thêm mức độ phơi nhiễm và tính dễ tổn thương) trong quy hoạch sử dụng đất.
- **Ma trận hoạt động và cường độ dựa trên PSI.** Cigna, Bianchini & Casagli (2013) đánh giá mức hoạt động và cường
  độ trượt lở từ dữ liệu PSI. Vận tốc LOS được chiếu lên mặt sườn (V_SLOPE = V_LOS / L2S) rồi so với hai ngưỡng:
  V_ACT (có dịch chuyển hay không) và V_INT, tức ranh giới "cực chậm / rất chậm" ở 16 mm/năm theo Cruden & Varnes.
  Ở khu vực Calabria, các tác giả hạ V_INT xuống 13 mm/năm để bù cho hiệu ứng lấy trung bình. Kết quả sau đó được tổ
  hợp với trạng thái ghi trong danh mục trượt lở thông qua các ma trận.
  - Bianchini et al. (2012) dùng PSI để rà soát diện rộng, tìm các "điểm nóng" trượt lở.
  - Ciampalini et al. (2016) dùng vận tốc PSInSAR để tinh chỉnh bản đồ tính nhạy cảm lập bằng Random Forest, thông
    qua một ma trận tiếp liên. **v1 được thiết kế theo hướng này: cường độ InSAR × một yếu tố thứ hai, tổ hợp trong
    một ma trận tường minh.**
- **Vùng biến dạng hoạt động (ADA).** Nhóm công trình này chuyển bản đồ PSI thành các đơn vị khoanh vẽ rồi phân loại
  chúng:
  - Barra et al. (2017) lấy ngưỡng ổn định bằng 2σ của bản đồ vận tốc, yêu cầu ít nhất 1,5 năm dữ liệu và bổ sung
    một chỉ số chất lượng.
  - Tomás et al. (2019) dùng ngưỡng k·σ với k = 1–2 và yêu cầu mỗi ADA có ít nhất 3 PS.
  - Navarro et al. (2020, ADAtools) phân loại ADA bằng các quy tắc địa hình đơn giản: trượt lở tiềm năng cần độ dốc
    ≥ 5°, còn sụt lún tiềm năng cần độ dốc ≤ 10° trên trầm tích Đệ Tứ.
  - Solari et al. (2020) tổng quan hơn 250 ứng dụng ở Ý.
- **Thang vận tốc.** Theo Cruden & Varnes (1996), được Hungr et al. (2014) dẫn lại: cực chậm < 16 mm/năm, rất chậm
  từ 16 mm/năm đến 1,6 m/năm, chậm đến 13 m/tháng. InSAR đo được hai cấp đầu.

### 2.2 Sụt lún: tốc độ, lún lệch và thiệt hại

- **Nguy cơ toàn cầu.** Herrera-García et al. (2021) lập bản đồ mối đe doạ sụt lún đất trên toàn cầu bằng cách tổ
  hợp các yếu tố nhạy cảm (thạch học, độ dốc, lớp phủ mặt đất, khí hậu) với xác suất suy giảm nước dưới đất.
- **Thiệt hại do lún lệch.** Hư hại nhà cửa và mạng lưới hạ tầng phụ thuộc vào lún *lệch* (góc biến dạng) nhiều hơn
  là vào bản thân tốc độ lún:
  - Skempton & MacDonald (1956) lấy 1/300 là ngưỡng bắt đầu nứt và 1/150 là ngưỡng thiệt hại kết cấu.
  - Bjerrum (1963) lấy 1/500 làm giới hạn an toàn cho công trình không cho phép nứt. Các giá trị này dẫn lại từ
    nguồn thứ cấp (§10).
  - Fernández-Torres et al. (2020, 2022) áp dụng các ngưỡng trên cho InSAR ở Mexico City: tính gradient ngang của
    sụt lún, quy đổi ra góc biến dạng và lấy 0,002 rad (1/500) làm ngưỡng thiệt hại.
  - Cigna & Tapete (2021) lập bản đồ nguy cơ nứt gãy bề mặt ở Mexico City từ gradient Sentinel-1.
- **Nước dưới đất và chuyển dịch theo mùa.** Trong hệ tầng chứa nước, mặt đất biến đổi theo mực áp lực: phần nâng –
  lún đàn hồi theo mùa bám theo bổ cập và khai thác, còn phần nén chặt không đàn hồi phản ánh suy giảm dài hạn.
  - Hoffmann et al. (2001) và Chaussard et al. (2014) chỉ ra biến dạng theo mùa cùng pha với mực áp lực. Chaussard
    et al. (2014, 2017) dự báo mực áp lực từ InSAR và dùng tương quan chéo để liên hệ biến dạng với mực nước và hạn
    hán.
  - Ở Tây Ban Nha, Tomás et al. (2010), Ezquerro et al. (2014), Bonì et al. (2015) và Béjar-Pizarro et al. (2017)
    đối chiếu sụt lún PSI với mực nước quan trắc (piezometric).
- **Hà Nội.**
  - Dang et al. (2014) dùng ảnh ALOS 2007–2011 và ghi nhận tốc độ sụt lún tới 68 mm/năm. Từ năm 2008, họ còn phát
    hiện các dao động nâng / lún theo mùa, gắn với bổ cập trong mùa mưa và khai thác trong mùa khô. Đây là bằng
    chứng trực tiếp cho chuỗi mưa → tầng chứa nước → mặt đất ngay tại thành phố của các dự án thử nghiệm GeoEyes.
  - Bui et al. (2021) liên hệ biến dạng Sentinel-1 giai đoạn 2016–2020 với mực áp lực đang hạ thấp.
  - Nguyen et al. (2022) và Bateson et al. (2023) bổ sung thành phần dài hạn và thành phần do xây dựng.
  - Ở đồng bằng sông Cửu Long: Erban et al. (2014) và Minderhoud et al. (2017).
- **Lượng mưa làm đại lượng đại diện cho bổ cập.** Phương pháp độ lệch mưa tích luỹ (CRD) mô tả biến đổi mực nước
  bằng tổng luỹ tiến của lượng mưa trừ đi giá trị trung bình (Bredenkamp et al. 1995; Xu & van Tonder 2001). GeoEyes
  dùng CRD làm số hạng tác động (§4.3).

### 2.3 Trượt lở chậm và lượng mưa

- Lacroix, Handwerger & Bièvre (2020) tổng quan về trượt lở chậm:
  - Tốc độ từ mm/năm đến m/năm, thường gặp ở vật liệu giàu sét và ở nơi có mưa mùa mạnh.
  - Tốc độ trượt biến đổi theo áp lực nước lỗ rỗng. Chẳng hạn, khối trượt Maca thực hiện 90% chuyển dịch cả năm chỉ
    trong 5 tháng mùa mưa.
- Handwerger et al. (2013) theo dõi mười khối trượt ở California bằng InSAR, số liệu mưa và lidar:
  - Các khối trượt tăng tốc **sau một độ trễ** kể từ khi mùa mưa bắt đầu, trong vòng khoảng 40 ngày.
  - Các tác giả kiểm định cơ chế khuếch tán áp lực nước lỗ rỗng, trong đó thời gian đáp ứng tỉ lệ với độ
    sâu²/hệ số khuếch tán.
- Các công trình sau đó phát triển thêm:
  - Handwerger et al. (2016, 2019) nghiên cứu ma sát suy giảm theo tốc độ (rate-weakening) và việc chuyển từ hạn hán
    sang mưa cực đoan đã đẩy khối trượt Mud Creek tới phá huỷ.
  - Bennett et al. (2016) cho thấy hạn hán làm các dòng đất (earthflow) chậm lại.
  - Bayer et al. (2018) dùng COSMO-SkyMed và Sentinel-1, ghi nhận đáp ứng theo mùa khác nhau tuỳ thạch học ở dãy
    Apennines.
  - Hu et al. (2020) định lượng tác động khí tượng – thuỷ văn trong không gian 4-D.
- **Dấu hiệu báo trước.** Gia tốc là chỉ báo quan trọng nhất:
  - Intrieri et al. (2018) phát hiện giai đoạn tăng tốc trước khi khối trượt Maoxian phá huỷ trong dữ liệu
    Sentinel-1.
  - Phương pháp nghịch đảo vận tốc ngoại suy 1/v về 0 (Fukuzono 1985; Voight 1988, 1989).
- **Khoảng trống dữ liệu.** Ở vùng núi dốc chịu gió mùa, InSAR mất độ kết hợp trong mùa mưa (Bekaert et al. 2020,
  Nepal).
- **Ngưỡng mưa** *kích hoạt* trượt lở nông, nhanh là một công cụ khác, dùng ở quy mô sự kiện:
  - ngưỡng cường độ – thời đoạn (Caine 1980; Guzzetti et al. 2008; tổng quan của Segoni et al. 2018);
  - mô hình mưa tiền kỳ (Crozier 1999; Glade 2000);
  - dự báo tức thời toàn cầu (LHASA, Kirschbaum & Stanley 2018).
- **Việt Nam.** Trượt lở do mưa ở vùng núi phía Bắc đã được ghi nhận nhiều, chẳng hạn ở Mù Cang Chải tháng 8/2023.
  Công trình giám sát trượt lở bằng InSAR duy nhất tìm được ở khu vực này là một báo cáo hội nghị tại Yên Bái (Tran
  et al. 2021). Chưa tìm thấy nghiên cứu chuỗi thời gian InSAR nào về trượt lở chậm ở miền Bắc Việt Nam được đăng trên
  tạp chí có bình duyệt: đây là một khoảng trống.

### 2.4 Thống kê với hàng nghìn chuỗi

- Tương quan chuyển dịch với lượng mưa không hề đơn giản: cả hai chuỗi đều tự tương quan và đều có chu kỳ mùa.
  - Vì thế, kiểm định tương quan thông thường sẽ thổi phồng ý nghĩa thống kê. Ebisuzaki (1997) dựng phân phối không
    (null) từ các chuỗi thay thế xáo pha ngẫu nhiên: các chuỗi này giữ nguyên phổ nhưng ngẫu nhiên hoá thời điểm.
- Một bản đồ kiểm định hàng nghìn ô, nên chỉ do ngẫu nhiên cũng đã có khoảng 5% số ô đạt p < 0,05. Thủ tục kiểm soát
  tỉ lệ phát hiện sai (FDR) giải quyết vấn đề này: Benjamini & Hochberg (1995), vẫn hợp lệ khi các phép kiểm định phụ
  thuộc dương (Benjamini & Yekutieli 2001). Wilks (2016) cho thấy các bản đồ bỏ qua bước này thường thổi phồng ý
  nghĩa thống kê đến mức nào.
- Với S chuỗi thay thế, giá trị p hoán vị không thể nhỏ hơn 1/(S+1). Khi số lần vượt ít, có thể xấp xỉ phần đuôi của
  phân phối không (Knijnenburg et al. 2009).
- **Yếu tố gây nhiễu.** Ở vùng khí hậu gió mùa, mưa và nhiệt độ cùng đạt cực đại một lúc. Giãn nở nhiệt của công
  trình cũng hiện ra trong chuỗi InSAR (Fornaro et al. 2013), nên tương quan với mưa chưa đủ để chứng minh nguyên nhân
  thuỷ văn.

### 2.5 Dữ liệu mưa

- **CHIRPS** (Funk et al. 2015; v3: Funk et al. 2026): lượng mưa tổng hợp từ ảnh hồng ngoại và trạm đo, độ phân giải
  0,05°, có từ năm 1981.
  - v3 cung cấp COG theo tháng và các sản phẩm ngày được phân rã bằng IMERG hoặc ERA5. Tệp readme của v3 khuyến nghị
    dùng tổng 5 ngày (pentad) hoặc tổng tháng thay cho giá trị ngày.
  - v2 ngừng cung cấp sau tháng 12/2026.
- **ERA5** (Hersbach et al. 2020): dữ liệu tái phân tích 0,25°, truy cập qua API lưu trữ của Open-Meteo (Zippenfenig
  2024), dùng làm phương án dự phòng. Tái phân tích làm trơn các đỉnh mưa đối lưu: tại Hà Nội tháng 6/2011, ERA5 cho
  224 mm trong khi CHIRPS cho 430 mm. Tuy vậy, khí hậu năm của hai nguồn khá gần nhau: P10 / P50 / P90 = 1442 / 1673 /
  2162 mm theo ERA5 và 1416 / 1633 / 2065 mm theo CHIRPS.
- **GPM IMERG** (Huffman et al. 2020, 2023): 0,1°, theo ngày, là đầu vào phù hợp cho các phân tích ở quy mô sự kiện
  (R5).

## 3. Giả thuyết

- **H1 (tốc độ).** Tốc độ InSAR theo hướng chuyển dịch dự kiến là chỉ báo đầu tiên về cường độ nguy cơ: hướng thẳng
  đứng với sụt lún, hướng xuôi dốc với trượt lở.
- **H2 (lún lệch).** Với sụt lún, khả năng gây thiệt hại phụ thuộc vào góc biến dạng tích luỹ trong một khoảng thời
  gian dự tính (horizon). Đại lượng này chỉ phụ thuộc vào *chênh lệch* tốc độ, nên không phụ thuộc vào cách tham chiếu
  của sản phẩm.
- **H3 (liên hệ mưa – biến dạng).** Ở nơi chuyển dịch phản ứng với mưa, chuyển dịch sau khi loại xu thế sẽ bám theo
  độ lệch mưa tích luỹ có độ trễ: d(t) = a + b·t + k·CRD(t − τ).
  - Với hệ tầng chứa nước, k < 0: mưa làm mặt đất nâng lên, tức là lún ít đi.
  - Với trượt lở, k > 0: mưa làm tăng chuyển dịch xuôi dốc.
  - Độ trễ τ phản ánh quá trình bổ cập hoặc khuếch tán áp lực nước lỗ rỗng. Từ đáp ứng k có thể dựng **kịch bản**:
    tốc độ trong một năm khô (P10) hoặc năm ướt (P90).
- **H4 (leo thang).** Nếu có đáp ứng với mưa đạt ý nghĩa thống kê, hoặc gia tốc đạt ý nghĩa thống kê theo hướng nguy
  cơ, thì mức nguy cơ được nâng lên cao hơn mức mà riêng tốc độ trung bình cho thấy.

H3 là giả thuyết cần kiểm định chứ không phải tiền đề: chỉ chấp nhận H3 ở những nơi vượt qua kiểm định chuỗi thay thế
với FDR tính trên toàn bản đồ.

## 4. Phương pháp (v1, đã triển khai)

### 4.1 Ô phân tích

- Các điểm được gộp vào ô vuông cạnh `cell_m` mét (mặc định 100 m) trên một lưới hệ mét cục bộ.
- Mỗi ô lưu chuỗi LOS trung vị, vectơ đơn vị LOS trung vị và độ kết hợp trung vị của các điểm trong ô.
- Mỗi ô cần tối thiểu `min_points` điểm (mặc định 3, giống yêu cầu cho một ADA của Tomás et al. 2019).
- Ô là đơn vị của bản đồ. Gộp theo ô giúp chuỗi ít nhạy với nhiễu, giữ số phép kiểm định ý nghĩa ở mức tính toán
  được, và phù hợp với quy mô tính độ dốc và gradient.

### 4.2 Địa hình và chế độ

- **Độ dốc.** DEM của dự án (`[stack].dem`: SRTM 1″, Copernicus GLO-30 hoặc một tệp riêng) được làm trơn bằng bộ
  lọc Gauss với σ bằng nửa ô, sau đó tính độ dốc trên khoảng một ô.
- **Vì sao phải làm trơn.** Mô hình số bề mặt (DSM) có cả nhà cửa và cây cối; nếu không làm trơn, khu đô thị sẽ xuất
  hiện độ dốc lớn ở mép các toà nhà. Nếu có, nên dùng DEM mặt đất trần (FABDEM, Hawker et al. 2022).
- **Chế độ.** Ô có độ dốc ≥ `landslide_min_slope_deg` (mặc định 10°) được xét ở chế độ `landslide`, các ô còn lại ở
  chế độ `subsidence`.
  - ADAtools dùng ngưỡng ≥ 5° cho trượt lở tiềm năng và ≤ 10° cho sụt lún. v1 chọn cận trên để đê và các nhiễu tạo
    tác của DSM đô thị vẫn thuộc chế độ sụt lún.
  - Ở Hà Nội, phân vị 99 của độ dốc sau làm trơn là 4,3°.

### 4.3 Chuyển dịch theo hướng nguy cơ và liên hệ mưa – biến dạng

**Phép chiếu.** Gọi **l** là vectơ đơn vị LOS hướng từ mặt đất lên vệ tinh, d_LOS là chuyển dịch LOS (dương khi
hướng về phía vệ tinh).

- **Ô sụt lún:** y = −d_LOS / l_u (giả định chuyển dịch thẳng đứng, lún lấy dấu dương).
- **Ô trượt lở:** y = d_LOS / (**s**·**l**), trong đó **s** là vectơ đơn vị theo hướng dốc nhất, nên chuyển dịch
  xuôi dốc mang dấu dương. Đây chính là phép chiếu L2S của Cigna et al. (2013).
  - Ô có |**s**·**l**| < `min_sensitivity` (0,3) được xếp là chưa đánh giá. Tại đó hướng nhìn chỉ ghi nhận được dưới
    30% chuyển dịch xuôi dốc, và phép chiếu sẽ khuếch đại nhiễu hơn ba lần.

**Dấu của kết quả.** y (lún hoặc xuôi dốc mang dấu dương) chỉ dùng bên trong phân tích để xếp lớp các ô. Mọi giá trị
ghi ra hoặc hiển thị đều giữ quy ước dấu của GeoEyes như trong sản phẩm: `rate_mm_yr`, chuỗi thời gian, gia tốc, các
hệ số liên hệ với mưa và nước ngầm (k, g, r) **mang dấu âm khi lún hoặc dịch xuống dốc**, dương khi nâng lên hoặc dịch
ngược dốc (mục "sign" trong `hazard.json`; schema `geoeyes.hazard/2`). Các phân tích tạo trước thay đổi này (schema 1)
được tự đổi dấu khi đọc.

**Tốc độ và độ ổn định.** Khớp tuyến tính cho tốc độ (mm/năm) và sai số chuẩn σ; khớp bậc hai cho gia tốc. Ô được coi
là ổn định (I0) khi tốc độ nhỏ hơn max(2 mm/năm, 2σ), theo:

- Barra et al. (2017): 2σ;
- Cigna et al. (2013): dải ±2 mm/năm.

**Tham chiếu.** Muốn xếp lớp cường độ, tốc độ phải tính tương đối so với nền ổn định.

- Sản phẩm tham chiếu vào một điểm thì giữ nguyên điểm đó.
- Sản phẩm tham chiếu vào *trung bình cảnh* sẽ kèm cảnh báo, vì tốc độ khi đó chỉ là tương đối.
- `reference_bbox` đặt lại tham chiếu cho các chuỗi theo trung vị của các ô nằm trong một vùng đã biết là ổn định.
- Chuyển dịch ngược hướng nguy cơ (tốc độ < −ngưỡng) chỉ được **gắn cờ** (`opposite_motion`), không xếp lớp.

**Lượng mưa.**

- **Số liệu tháng.** Mưa tháng lấy tại pixel CHIRPS chứa ô, từ `max_lag_months` tháng trước lần chụp đầu tiên đến
  lần chụp cuối cùng.
- **Tổng năm.** Từ tổng mưa năm trong giai đoạn chuẩn khí hậu WMO 1991–2020, tính lượng mưa năm khô (P10) và năm
  ướt (P90) cho từng pixel.
- **Dự phòng.** Nếu không đọc được CHIRPS thì dùng ERA5, và bản tóm tắt ghi rõ điều này.
- **CRD.** CRD(t) = Σ(P_month − P̄), với P̄ là giá trị trung bình trong cửa sổ phân tích; trong mỗi tháng, CRD biến
  thiên tuyến tính. Tháng thiếu số liệu được tính bằng P̄; pixel thiếu quá 20% thì không đánh giá.

**Mô hình liên hệ.** Với mỗi ô, mô hình có dạng

    y(t) = a + b·t + k·CRD(t − τ) + ε,       τ ∈ {0, 1, …, max_lag_months}

Nếu dị thường tốc độ bám theo dị thường mưa có độ trễ, tức v(t) − b = k·(P(t − τ) − P̄), thì lấy tích phân sẽ được
đúng mô hình trên. Do đó cùng một dạng mô hình dùng được cho cả mực áp lực tầng chứa nước (Bredenkamp; Xu & van
Tonder) lẫn vận tốc trượt lở (Handwerger et al. 2013).

- **b** là xu thế đã loại ảnh hưởng của mưa.
- **k** là độ nhạy, tính bằng mm chuyển dịch trên mỗi mm độ lệch mưa (báo cáo theo 100 mm).
- **τ** được chọn tại giá trị |tương quan riêng phần| lớn nhất giữa y và CRD(t − τ), sau khi đã loại ảnh hưởng của
  [1, t].

**Ý nghĩa thống kê.**

1. Lặp lại việc dò độ trễ trên `n_surrogates` (500) bản sao xáo pha ngẫu nhiên của dị thường mưa tháng (Ebisuzaki
   1997). Mỗi chuỗi thay thế giữ nguyên phổ nhưng có thời điểm ngẫu nhiên.
2. p là tỉ lệ chuỗi thay thế có |r| tốt nhất đạt hoặc vượt |r| quan sát. Vì mỗi chuỗi thay thế cũng được chọn lại độ
   trễ, kiểm định đã tính đến cả bước chọn độ trễ.
3. Khi có dưới 10 chuỗi thay thế đạt mức đó, p được tính từ phân phối chuẩn khớp với Fisher z của cực đại dưới giả
   thuyết không (theo Knijnenburg et al. 2009). Không có phần đuôi này, p không thể nhỏ hơn 1/501, và FDR trên toàn
   bản đồ sẽ không bao giờ phát hiện được một vùng liên hệ nhỏ. Unit test `test_assess_end_to_end` minh hoạ đúng
   trường hợp này.
4. Ô được coi là **có liên hệ** khi giá trị q Benjamini–Hochberg, tính trên toàn bộ các ô được kiểm định, ≤ `alpha`
   (0,05).

**Điều kiện.** Phân tích liên hệ cần chuỗi dài ít nhất `min_span_months` (12) tháng và có ít nhất `min_epochs` (12)
lần chụp, tức tối thiểu một chu kỳ mùa.

**Kịch bản mưa.** Với các ô có liên hệ:

    rate_dry = b + k·(P10_annual − 12·P̄)
    rate_wet = b + k·(P90_annual − 12·P̄)

Đây là tốc độ trong một năm khô hoặc năm ướt theo đáp ứng đã khớp. Ngoại suy đáp ứng tuyến tính cho các năm cực đoan
là giả định gần đúng bậc nhất (§8).

### 4.4 Các lớp

**Cường độ I.** Tốc độ được xét theo hướng nguy cơ. Ở các ô có liên hệ mưa đạt ý nghĩa thống kê, lấy giá trị bất lợi
nhất trong ba tốc độ: quan sát, năm khô và năm ướt.

| Lớp | Sụt lún (thẳng đứng, mm/năm) | Trượt lở (xuôi dốc, mm/năm) |
|---|---|---|
| I0 | < max(2, 2σ) hoặc chuyển dịch ngược hướng | < max(2, 2σ) hoặc chuyển dịch ngược hướng |
| I1 | ngưỡng ổn định … 10 | ngưỡng ổn định … 16 (cực chậm, Cruden & Varnes) |
| I2 | 10 … 30 | 16 … 160 (nửa dưới cấp rất chậm) |
| I3 | ≥ 30 | ≥ 160 (nửa trên cấp rất chậm, gần giới hạn đo của InSAR) |

Gia tốc đạt ý nghĩa thống kê theo hướng nguy cơ sẽ nâng I thêm một lớp (Intrieri et al. 2018). Đạt ý nghĩa ở đây
nghĩa là |gia tốc / sai số của nó| ≥ 3 trên chuỗi dài ít nhất 18 tháng.

**Tổn hại tiềm tàng S** (lớp phụ).

- **Sụt lún: góc biến dạng.** β = giá trị lớn nhất của |v_i − v_j| · T / L xét trên 8 ô lân cận, với
  T = `horizon_yr` (10 năm) và L là khoảng cách giữa tâm hai ô. Các lớp phân theo các giới hạn thiệt hại:

| Lớp | β | Ý nghĩa |
|---|---|---|
| S0 | < 1/500 | dưới giới hạn an toàn của Bjerrum |
| S1 | 1/500 … 1/300 | vượt giới hạn an toàn (Fernández-Torres et al. 2020: 0.002 rad) |
| S2 | 1/300 … 1/150 | bắt đầu nứt (Skempton & MacDonald) |
| S3 | ≥ 1/150 | thiệt hại kết cấu (Skempton & MacDonald) |

- **Trượt lở: tính nhạy cảm.** Các lớp 0–3 lấy từ raster do người dùng cung cấp (`susceptibility`). Nếu không có,
  tạm dùng các lớp độ dốc 15° / 25° / 35° cho đến khi có mô hình tính nhạy cảm thực thụ (R4).

### 4.5 Ma trận nguy cơ

Ma trận nguy cơ mặc định (do chuyên gia chọn, cấu hình được qua `matrix`) cho mức nguy cơ ứng với từng cặp lớp cường
độ và tổn hại tiềm tàng:

| | S0 | S1 | S2 | S3 |
|---|---|---|---|---|
| **I3** | cao | cao | rất cao | rất cao |
| **I2** | trung bình | trung bình | cao | rất cao |
| **I1** | thấp | thấp | trung bình | cao |
| **I0** | rất thấp | rất thấp | thấp | thấp |

- Cường độ InSAR quyết định phần lớn mức nguy cơ.
- Yếu tố thứ hai nâng mức nguy cơ ở phía cao, tương tự các ma trận dựa trên PSI của Cigna et al. (2013) và
  Ciampalini et al. (2016).
- Ô ổn định nằm trên sườn dốc lớn hoặc trong vùng góc biến dạng cao vẫn ở mức "thấp" chứ không phải "rất thấp": đây
  là tín hiệu *tiềm năng* theo cách hiểu của Ciampalini et al.

### 4.6 Đầu ra

Kết quả được ghi vào `<project>/analyses/hazard/<product_id>/`:

- `cells.parquet`: mỗi ô một dòng, chứa mọi giá trị trung gian (tốc độ, σ, ngưỡng ổn định, gia tốc, độ trễ, r, p, q,
  k, xu thế đã loại ảnh hưởng của mưa, tốc độ năm khô / năm ướt, I quan sát và I cuối cùng, β, S, mức nguy cơ, các
  cờ);
- `cells_ts.npy`: chuỗi thời gian theo hướng chuyển dịch;
- `rain.npz`: lưới mưa tháng và mưa năm;
- `hazard.json`: tham số, tóm tắt, nguồn dữ liệu và cảnh báo;
- `hazard.gpkg`: các ô vuông để mở trong QGIS;
- `manifest.json`: ghi nhận sản phẩm làm đầu vào.

Sản phẩm luôn được giữ nguyên, không bị sửa đổi; có thể chạy lại phân tích với tham số khác.

## 5. Tham số và căn cứ chọn giá trị mặc định

Mọi tham số nằm trong mục `[postprocess.hazard]` của `project.toml`; có thể ghi đè bằng `geoeyes hazard --set
key=value` hoặc thay đổi ngay trên ứng dụng web.

| Khoá | Mặc định | Nguồn / lý do |
|---|---|---|
| `cell_m` | 100 | Quy mô phân tích. Phải lớn hơn kích thước công trình trên DSM; cũng là L trong góc biến dạng |
| `min_points` | 3 | Tomás et al. 2019 (≥ 3 PS mỗi ADA); Cigna et al. 2013 (3–5 PS mỗi khối trượt) |
| `stable_floor_mm_yr`, `stable_sigma` | 2, 2 | Cigna et al. 2013 (dải ±2 mm/năm); Barra et al. 2017 (2σ) |
| `subsidence_breaks` | 10, 30 | **Lựa chọn địa phương, cần hiệu chỉnh (R3).** 30 mm/năm tương ứng 0.3 m sau 10 năm |
| `landslide_breaks` | 16, 160 | Cruden & Varnes 1996: 16 mm/năm; cấp rất chậm chia đôi tại điểm giữa theo thang logarit |
| `distortion_breaks` | 1/500, 1/300, 1/150 | Bjerrum 1963; Skempton & MacDonald 1956; Fernández-Torres et al. 2020 |
| `horizon_yr` | 10 | Khoảng thời gian quy hoạch. Với `horizon_yr = 1`, β là gradient ngang trong một năm |
| `landslide_min_slope_deg` | 10 | Quy tắc ADAtools (trượt lở ≥ 5°, sụt lún ≤ 10°), lấy cận trên |
| `min_sensitivity` | 0.3 | Phép chiếu L2S (Cigna et al. 2013); giới hạn hệ số khuếch đại nhiễu ở 3.3 |
| `slope_breaks` | 15, 25, 35 | **Giá trị tạm thời.** Thay bằng raster tính nhạy cảm (R4) |
| `max_lag_months` | 6 | Độ trễ vài tuần đến vài tháng (Handwerger et al. 2013; dao động theo mùa của Dang et al. 2014) |
| `n_surrogates`, `alpha`, `fdr` | 500, 0.05, true | Ebisuzaki 1997; Benjamini & Hochberg 1995; Wilks 2016 |
| `min_span_months`, `min_epochs` | 12, 12 | Tối thiểu một chu kỳ mùa. Barra et al. (2017) yêu cầu 1.5 năm cho ADA |
| `accel_t`, `accel_min_span_months` | 3, 18 | Ngưỡng ý nghĩa thận trọng cho số hạng bậc hai, trên chuỗi dài ít nhất 1.5 năm |
| `climate_years` | 1991, 2020 | Chuẩn khí hậu tiêu chuẩn của WMO |
| `rain_source` | auto | CHIRPS (kết hợp số liệu trạm đo, 0.05°); ERA5 nếu không đọc được CHIRPS |
| `reference_bbox` | none | Nền ổn định để tính cường độ (§4.3) |
| `gnss_tie` | false | Áp dụng hiệu chỉnh theo hệ thống định vị vệ tinh toàn cầu (GNSS) cho sản phẩm, xem [gnss-insar-calibration.md](gnss-insar-calibration.md) |
| `matrix` | §4.5 | Ma trận chuyên gia theo cách của Cigna et al. 2013 |

## 6. Trình tự nghiên cứu

Công việc chia thành bảy bước, từ R0 đến R6. Mỗi bước nêu câu hỏi, đầu vào, phương pháp, đầu ra và tiêu chí chấp
nhận. v1 đã thực hiện R0, R1 và phần tính toán của R2, đủ dùng như một công cụ sàng lọc trong vận hành. Các bước còn
lại phải hoàn thành trước khi bản đồ có thể làm căn cứ ra quyết định.

### R0 — Kiểm tra dữ liệu và tham chiếu *(đã có trong v1, chạy ở mỗi lần phân tích)*

- **Câu hỏi:** sản phẩm có đủ điều kiện để đánh giá nguy cơ không?
- **Phương pháp:**
  - kiểm tra độ dài chuỗi (≥ 12 tháng để phân tích liên hệ, ≥ 18 tháng để xét gia tốc), số lần chụp và độ phủ ô;
  - kiểm tra cách tham chiếu: một điểm, trung bình cảnh hay một vùng ổn định;
  - kiểm tra có dữ liệu mưa hay không và lấy từ nguồn nào.
- **Đầu ra:** các cảnh báo trong `hazard.json`.
- **Tiêu chí:** không đọc bản đồ cường độ nào khi chưa tham chiếu về nền ổn định.
- **Bổ sung ngày 2026-10-25:** gắn vào GNSS (`gnss_tie`, [gnss-insar-calibration.md](gnss-insar-calibration.md)).
- **Cần bổ sung:** đối chiếu vùng tham chiếu với địa chất.

### R1 — Chẩn đoán liên hệ mưa – biến dạng *(đã có trong v1)*

- **Câu hỏi:** chuyển dịch bám theo lượng mưa ở đâu, với độ trễ bao nhiêu và theo dấu nào?
- **Phương pháp:** mô hình CRD kèm kiểm định chuỗi thay thế và FDR (§4.3), áp dụng cho từng ô và riêng cho từng chế
  độ.
- **Đầu ra:**
  - bản đồ r, τ và k; tỉ lệ ô có liên hệ;
  - tốc độ năm khô / năm ướt.
- **Tiêu chí:**
  - phương pháp tìm lại được đáp ứng cài sẵn với đúng độ trễ và k (unit test: phát hiện ≥ 95% số ô cài sẵn, báo động
    sai trên nhiễu không quá 5%);
  - với dữ liệu thực, tỉ lệ thô các ô có p < α phải lớn hơn α thì mới diễn giải các ô có liên hệ.

### R2 — Xác định nguyên nhân: mưa, nước dưới đất, nhiệt độ

- **Câu hỏi:** liên hệ này có nguồn gốc thuỷ văn hay không?
- **Phương pháp:**
  - thêm nhiệt độ 2 m của ERA5 làm biến hồi quy thứ hai, d = a + b·t + k·CRD(t − τ) + c·T(t), để tách ảnh hưởng giãn
    nở nhiệt (Fornaro et al. 2013);
  - đối chiếu với số liệu quan trắc mực nước ở những nơi có (Hà Nội: Bui et al. 2021; Tây Ban Nha: Béjar-Pizarro et
    al. 2017);
  - từ v1.1, mỗi ô còn được kiểm định liên hệ với trữ lượng nước ngầm của NASA GLDAS (đồng hoá GRACE), như một chẩn
    đoán: xem [groundwater-insar.md](groundwater-insar.md);
  - so sánh sản phẩm quỹ đạo lên và quỹ đạo xuống để tách chuyển dịch thẳng đứng và nằm ngang.
- **Đầu ra:** với mỗi vùng có liên hệ, phần do mưa, phần do nhiệt độ và phần do mực áp lực giải thích.
- **Tiêu chí:** hệ số của mưa vẫn đạt ý nghĩa thống kê khi đã đưa nhiệt độ vào mô hình.

### R3 — Hiệu chỉnh các lớp

- **Câu hỏi:** các giới hạn lớp có phân biệt được nền đã bị thiệt hại với nền chưa bị thiệt hại không?
- **Phương pháp:**
  - lập danh mục: vết nứt công trình và báo cáo thiệt hại, các lần sửa đường hoặc đường ống, các khối trượt đã
    khoanh vẽ kèm trạng thái;
  - trên một nửa khu vực, chọn các giới hạn cường độ và ma trận phân tách danh mục tốt nhất, dựa trên đường cong ROC
    và AUC của từng giới hạn lớp; kiểm tra trên nửa còn lại.
- **Đầu ra:** bộ `subsidence_breaks`, `landslide_breaks` và `matrix` riêng cho địa phương, kèm AUC.
- **Tiêu chí:** AUC trên nửa kiểm tra ≥ 0,7, và thứ hạng ổn định giữa hai nửa.

### R4 — Mô hình tính nhạy cảm cho trượt lở

- **Câu hỏi:** trượt lở có thể xảy ra ở đâu, bất kể hiện tại có chuyển dịch hay không?
- **Phương pháp:**
  - mô hình tính nhạy cảm bằng thống kê hoặc học máy (tổng quan: Reichenbach et al. 2018), dựa trên độ dốc, độ cong,
    thạch học, lớp phủ mặt đất, khoảng cách tới đường giao thông và sông, cùng một danh mục trượt lở;
  - các lớp 0–3 của mô hình thay cho lớp độ dốc tạm thời thông qua `susceptibility`;
  - tinh chỉnh bằng InSAR theo cách của Ciampalini et al. (2016).
- **Đầu ra:** raster tính nhạy cảm và ma trận đã tinh chỉnh.
- **Tiêu chí:** tỉ lệ thành công và tỉ lệ dự báo của mô hình trên các khối trượt để riêng cho kiểm tra.

### R5 — Kích hoạt ở quy mô sự kiện và cảnh báo sớm

- **Câu hỏi:** khi nào trượt lở dễ bị kích hoạt?
- **Phương pháp:**
  - dùng mưa ngày (CHIRPS v3 ngày hoặc IMERG) với ngưỡng cường độ – thời đoạn hoặc ngưỡng mưa tiền kỳ (Caine 1980;
    Guzzetti et al. 2008; Segoni et al. 2018; Glade 2000), hiệu chỉnh trên các sự kiện ở Việt Nam (chẳng hạn Mù Cang
    Chải, 2023);
  - kết hợp với tính nhạy cảm thành hệ dự báo tức thời tương tự LHASA (Kirschbaum & Stanley 2018);
  - với các ô InSAR đang tăng tốc, kiểm tra bằng phương pháp nghịch đảo vận tốc (Fukuzono 1985; Voight 1989;
    Intrieri et al. 2018);
  - nối với chức năng cảnh báo của ứng dụng web.
- **Đầu ra:** cảnh báo theo khu vực và thời gian.
- **Tiêu chí:** xác suất phát hiện và tỉ lệ báo động sai trên các sự kiện đã xảy ra.

### R6 — Từ nguy cơ đến rủi ro

- **Câu hỏi:** những đối tượng nào bị phơi nhiễm?
- **Phương pháp:**
  - chồng xếp bản đồ nguy cơ với công trình, mạng lưới hạ tầng và dân cư: rủi ro = nguy cơ × mức độ phơi nhiễm × tính
    dễ tổn thương (Fell et al. 2008);
  - tham khảo chỉ số rủi ro sụt lún của Mexico City trong Fernández-Torres et al. (2020, 2022).
- **Đầu ra:** phân vùng rủi ro ở quy mô quy hoạch.

## 7. Kết quả đầu tiên trên các dự án GeoEyes

Ngày 2026-10-25, bốn sản phẩm được chạy với tham số mặc định, ô 100 m, giữ nguyên tham chiếu gốc của từng sản phẩm.
Với Hanoi CSK, số liệu mưa đọc từ CHIRPS. Với ba sản phẩm còn lại, máy chủ CHIRPS từ chối yêu cầu (giới hạn tần suất
truy cập) nên hệ thống chuyển sang ERA5 và ghi rõ trong bản tóm tắt.

| Sản phẩm | Giai đoạn | Số lần chụp | Số ô | Liên hệ: đã kiểm định · p < 0.05 thô · có ý nghĩa (FDR) | β ≥ 1/500 | Nguy cơ (km²) |
|---|---|---|---|---|---|---|
| Hanoi CSK asc v3 | 2011-07 → 2014-12 (41 tháng) | 18 | 6 362 | 6 362 · 233 (3.7%) · **0** | 0 | rất thấp 58.2, thấp 5.5 |
| Hanoi S1 desc 091 v4 | 2025-10 → 2026-10 (12.5 tháng) | 26 | 15 071 | 15 071 · 251 (1.7%) · **0** | 0 | rất thấp 136.1, thấp 11.6, trung bình 3.0 |
| Mexico S1 asc 078 v6 | 2024-05 → 2024-10 (6 tháng) | 16 | 44 750 | chưa đánh giá (< 12 tháng) | 9 314 | sụt lún cao 113.9, rất cao 10.7 |
| Mexico Capella asc v4 | 2024-06 → 2024-08 (1.6 tháng) | 18 | 1 735 | chưa đánh giá | 1 132 | sụt lún cao 1.9, rất cao 1.9 |

**Diễn giải.**

- **Hà Nội: không có liên hệ mưa – biến dạng.** Không phát hiện được liên hệ với mưa ở cả hai sản phẩm Hà Nội: tỉ lệ
  thô các ô có p < 0,05 *thấp hơn* 5%, đúng như kỳ vọng khi giả thuyết không đúng.
  - Cách lấy mẫu của CSK (18 lần chụp không đều, khoảng 3 lần mỗi mùa mưa) và chỉ một năm dữ liệu S1 là quá thưa để
    bắt được tín hiệu theo mùa.
  - Cả hai sản phẩm đều tham chiếu vào trung bình cảnh. Dang et al. (2014) ghi nhận dao động theo mùa ở các vùng ven
    đô đang sụt lún (Hoàng Mai, Hà Đông, Hoài Đức), trong khi AOI của CSK là khu trung tâm thành phố.
  - **Đây là kết quả âm tính, không phải thất bại.** R1 cần một chuỗi S1 dài hơn trên vùng ven đô, tham chiếu về nền
    ổn định.
- **Mexico City: trường hợp đối chứng.** Trong khoảng 10 năm, lún lệch vượt giới hạn 1/500 của Bjerrum ở 9 314 ô S1
  (93 km²) và vượt 1/150 (thiệt hại kết cấu) ở 122 ô.
  - Cả hai sản phẩm Mexico đều mang tính tương đối: S1 so với trung bình cảnh, Capella so với một điểm nằm trong vùng
    đang sụt lún. Vì vậy có 19 087 ô S1 trông như đang chuyển dịch *lên*.
  - Đó là lý do cường độ được xét theo hướng, và cũng là lý do lần chạy phát cảnh báo. Cần chạy lại với
    `reference_bbox` đặt trên nền đá núi lửa ổn định trước khi đọc cường độ. Riêng β không phụ thuộc vào tham chiếu.
- **Mexico S1: các ô trượt lở.** 912 ô ở chế độ trượt lở trên các đồi núi lửa trong cảnh S1 chỉ có một hình học
  chụp, nên sụt lún thẳng đứng trên sườn dốc có thể bị hiểu nhầm thành chuyển dịch xuôi dốc (§8).

## 8. Hạn chế

1. **Một hình học chụp.** Chuyển dịch được giả định là thẳng đứng (sụt lún) hoặc xuôi dốc (trượt lở). Vì vậy chuyển
   dịch ngang trong các phễu lún, hay sụt lún trên sườn dốc, sẽ bị quy sai. Phân tích tổ hợp quỹ đạo lên và quỹ đạo
   xuống (R2) sẽ khắc phục hạn chế này.
2. **Tham chiếu.** Các lớp cường độ chỉ đáng tin khi tham chiếu về nền ổn định đáng tin (§4.3, §7).
3. **Đáp ứng tuyến tính.** Kịch bản mưa ngoại suy một hệ số k tuyến tính cho năm khô và năm ướt. Thực tế, đáp ứng
   của trượt lở là phi tuyến: có ngưỡng, có suy giảm ma sát theo tốc độ và có thể dẫn tới phá huỷ mất kiểm soát
   (Handwerger et al. 2016, 2019). Đáp ứng của tầng chứa nước còn phụ thuộc vào khai thác, yếu tố mà lượng mưa không
   phản ánh được.
4. **Tương quan không phải nhân quả.** Ở vùng khí hậu gió mùa, mưa và nhiệt độ biến thiên cùng nhau (R2).
5. **Dữ liệu mưa thô.** Pixel CHIRPS là 0,05° (khoảng 5,5 km); ERA5 là 0,25° và làm trơn các đỉnh mưa đối lưu. Vì
   thế liên hệ được xét theo từng pixel mưa chứ không theo từng sườn dốc.
6. **Khoảng trống độ kết hợp.** Mất kết hợp trong mùa mưa làm lệch mẫu trên các sườn có thực phủ (Bekaert et al.
   2020): những ô còn lại có thể chính là những ô ổn định.
7. **Giới hạn chưa được hiệu chỉnh.** Các giới hạn cường độ sụt lún, lớp độ dốc tạm thời và ma trận vẫn là lựa chọn
   chuyên gia cho đến khi hoàn thành R3 và R4.
8. **DSM.** SRTM và GLO-30 có chứa công trình. Làm trơn giảm được nhiễu tạo tác nhưng không loại bỏ hết (nên dùng
   FABDEM).
9. **Không phải xác suất.** Các mức nguy cơ là lớp định tính, không phải xác suất hằng năm (Fell et al. 2008).

## 9. Triển khai

| Thành phần | Vị trí |
|---|---|
| Lưới mưa (CHIRPS tháng và năm theo pixel, dự phòng ERA5, bộ nhớ đệm, đọc giãn cách để không quá tải máy chủ) | `src/geoeyes/ancillary/rainfall.py` |
| CRD, mô hình liên hệ, chuỗi thay thế, giá trị p phần đuôi, FDR, khớp tuyến tính và bậc hai | `src/geoeyes/hazard/coupling.py` |
| Độ dốc và vectơ xuôi dốc từ DEM đã làm trơn; raster tính nhạy cảm | `src/geoeyes/hazard/terrain.py` |
| Các lớp, góc biến dạng, ma trận | `src/geoeyes/hazard/zoning.py` |
| Điều phối, tham số, đầu ra | `src/geoeyes/hazard/assess.py` |
| CLI `geoeyes hazard <project> [--product ID] [--set key=value]` | `src/geoeyes/cli/main.py` |
| API `/api/projects/{p}/products/{id}/hazard[...]` | `src/geoeyes/api/hazard.py` |
| Trang web **Phân tích chuyên đề** (bản đồ, lớp bản đồ, chú giải và ma trận, bảng thông tin ô) và chương 2 của trang Nguyên lý (phương pháp) | `webapp/src/pages/Hazard.tsx`, `webapp/src/pages/LearnHazard.tsx` |
| Test (tìm lại đáp ứng cài sẵn, chuỗi thay thế, FDR, các lớp, chạy đầu cuối, đặt lại tham chiếu) | `tests/unit/hazard/test_hazard.py` |

**Truy cập CHIRPS.** Máy chủ của Climate Hazards Center hạn chế các máy khách đọc nhiều tệp cùng lúc: `robots.txt`
của máy chủ quy định độ trễ thu thập 10 s. Vì thế GeoEyes đọc lần lượt từng tệp, lưu đệm vĩnh viễn mọi giai đoạn đã
công bố (`<workspace>/cache/rainfall/chirps3_*.npz`) và dừng ngay khi bị từ chối lần đầu. Lần chạy nào bị máy chủ
chặn sẽ chuyển sang ERA5 và ghi rõ điều đó.

Ví dụ cấu hình:

```toml
[postprocess.hazard]
cell_m = 100
horizon_yr = 10
reference_bbox = [105.770, 21.010, 105.780, 21.020]   # stable ground (example)
susceptibility = "D:/data/landslide_susceptibility_classes.tif"   # optional, classes 0..3
```

## 10. Tài liệu tham khảo

Tất cả DOI dưới đây đã được kiểm tra trên Crossref hoặc DataCite vào tháng 10/2026. Các mục đánh dấu † được trích qua
danh mục thư viện hoặc nguồn thứ cấp: số liệu của các mục này lấy từ những bài báo trích dẫn lại, không phải từ bản
gốc.

**Khung phân tích nguy cơ và phương pháp PSI**

- Barra A, Solari L, Béjar-Pizarro M, Monserrat O, Bianchini S, Herrera G, Crosetto M, Sarro R, et al. (2017) A methodology to detect and update active deformation areas based on Sentinel-1 SAR images. *Remote Sensing* 9(10):1002. https://doi.org/10.3390/rs9101002
- Bianchini S, Cigna F, Righini G, Proietti C, Casagli N (2012) Landslide HotSpot Mapping by means of Persistent Scatterer Interferometry. *Environmental Earth Sciences* 67(4):1155–1172. https://doi.org/10.1007/s12665-012-1559-5
- Ciampalini A, Raspini F, Lagomarsino D, Catani F, Casagli N (2016) Landslide susceptibility map refinement using PSInSAR data. *Remote Sensing of Environment* 184:302–315. https://doi.org/10.1016/j.rse.2016.07.018
- Cigna F, Bianchini S, Casagli N (2013) How to assess landslide activity and intensity with Persistent Scatterer Interferometry (PSI): the PSI-based matrix approach. *Landslides* 10(3):267–283. https://doi.org/10.1007/s10346-012-0335-7
- Cruden DM, Varnes DJ (1996) Landslide types and processes. In: Turner AK, Schuster RL (eds) *Landslides: Investigation and Mitigation*, TRB Special Report 247, 36–75. †
- Fell R, Corominas J, Bonnard C, Cascini L, Leroi E, Savage WZ (2008) Guidelines for landslide susceptibility, hazard and risk zoning for land use planning. *Engineering Geology* 102(3–4):85–98. https://doi.org/10.1016/j.enggeo.2008.03.022
- Hungr O, Leroueil S, Picarelli L (2014) The Varnes classification of landslide types, an update. *Landslides* 11(2):167–194. https://doi.org/10.1007/s10346-013-0436-y
- Navarro JA, Tomás R, Barra A, Pagán JI, Reyes-Carmona C, Solari L, Vinielles JL, Falco S, et al. (2020) ADAtools: Automatic detection and classification of active deformation areas from PSI displacement maps. *ISPRS Int. J. Geo-Information* 9(10):584. https://doi.org/10.3390/ijgi9100584
- Notti D, Herrera G, Bianchini S, Meisina C, García-Davalillo JC, Zucca F (2014) A methodology for improving landslide PSI data analysis. *Int. J. Remote Sensing* 35(6):2186–2214. https://doi.org/10.1080/01431161.2014.889864
- Reichenbach P, Rossi M, Malamud BD, Mihir M, Guzzetti F (2018) A review of statistically-based landslide susceptibility models. *Earth-Science Reviews* 180:60–91. https://doi.org/10.1016/j.earscirev.2018.03.001
- Solari L, Del Soldato M, Raspini F, Barra A, Bianchini S, Confuorto P, Casagli N, Crosetto M (2020) Review of satellite interferometry for landslide detection in Italy. *Remote Sensing* 12(8):1351. https://doi.org/10.3390/rs12081351
- Tomás R, Pagán JI, Navarro JA, Cano M, Pastor JL, Riquelme A, Cuevas-González M, Crosetto M, et al. (2019) Semi-automatic identification and pre-screening of geological–geotechnical deformational processes using persistent scatterer interferometry datasets. *Remote Sensing* 11(14):1675. https://doi.org/10.3390/rs11141675
- Varnes DJ, IAEG Commission on Landslides (1984) *Landslide hazard zonation: a review of principles and practice.* UNESCO, Natural Hazards 3. †

**Sụt lún, thiệt hại và nước dưới đất**

- Bateson L, Novellino A, Hussain E, Arnhardt R, Nguyen HK, et al. (2023) Urban development induced subsidence in deltaic environments: a case study in Hanoi, Vietnam. *Int. J. Applied Earth Observation and Geoinformation* 125:103585. https://doi.org/10.1016/j.jag.2023.103585
- Béjar-Pizarro M, Ezquerro P, Herrera G, Tomás R, Guardiola-Albert C, et al. (2017) Mapping groundwater level and aquifer storage variations from InSAR measurements in the Madrid aquifer, Central Spain. *Journal of Hydrology* 547:678–689. https://doi.org/10.1016/j.jhydrol.2017.02.011
- Bjerrum L (1963) Allowable settlement of structures. *Proc. European Conf. on Soil Mechanics and Foundation Engineering*, Wiesbaden, vol. 2. †
- Bonì R, Herrera G, Meisina C, et al. (2015) Twenty-year advanced DInSAR analysis of severe land subsidence: the Alto Guadalentín Basin (Spain) case study. *Engineering Geology* 198:40–52. https://doi.org/10.1016/j.enggeo.2015.08.014
- Bredenkamp DB, Botha LJ, van Tonder GJ (1995) *Manual on quantitative estimation of groundwater recharge and aquifer storativity.* Water Research Commission TT 73/95, Pretoria. †
- Bui LK, Le PV, Dao PD, Long NQ, Pham HV, Tran HH, Xie L (2021) Recent land deformation detected by Sentinel-1A InSAR data (2016–2020) over Hanoi, Vietnam, and the relationship with groundwater level change. *GIScience & Remote Sensing* 58(2):161–179. https://doi.org/10.1080/15481603.2020.1868198
- Chaussard E, Bürgmann R, Shirzaei M, Fielding EJ, Baker B (2014) Predictability of hydraulic head changes and characterization of aquifer-system and fault properties from InSAR-derived ground deformation. *J. Geophys. Res. Solid Earth* 119(8):6572–6590. https://doi.org/10.1002/2014JB011266
- Chaussard E, Milillo P, Bürgmann R, Perissin D, Fielding EJ, Baker B (2017) Remote sensing of ground deformation for monitoring groundwater management practices: application to the Santa Clara Valley during the 2012–2015 California drought. *J. Geophys. Res. Solid Earth* 122(10):8566–8582. https://doi.org/10.1002/2017JB014676
- Cigna F, Tapete D (2021) Present-day land subsidence rates, surface faulting hazard and risk in Mexico City with 2014–2020 Sentinel-1 IW InSAR. *Remote Sensing of Environment* 253:112161. https://doi.org/10.1016/j.rse.2020.112161
- Dang VK, Doubre C, Weber C, Gourmelen N, Masson F (2014) Recent land subsidence caused by the rapid urban development in the Hanoi region (Vietnam) using ALOS InSAR data. *Natural Hazards and Earth System Sciences* 14(3):657–674. https://doi.org/10.5194/nhess-14-657-2014
- Erban LE, Gorelick SM, Zebker HA (2014) Groundwater extraction, land subsidence, and sea-level rise in the Mekong Delta, Vietnam. *Environmental Research Letters* 9(8):084010. https://doi.org/10.1088/1748-9326/9/8/084010
- Ezquerro P, Herrera G, Marchamalo M, Tomás R, Béjar-Pizarro M, Martínez R (2014) A quasi-elastic aquifer deformational behavior: Madrid aquifer case study. *Journal of Hydrology* 519:1192–1204. https://doi.org/10.1016/j.jhydrol.2014.08.040
- Fernández-Torres E, Cabral-Cano E, Solano-Rojas D, Havazli E, Salazar-Tlaczani L (2020) Land subsidence risk maps and InSAR based angular distortion structural vulnerability assessment: an example in Mexico City. *Proc. IAHS* 382:583–587. https://doi.org/10.5194/piahs-382-583-2020
- Fernández-Torres E, Cabral-Cano E, Novelo-Casanova DA, Solano-Rojas D, Havazli E, Salazar-Tlaczani L (2022) Risk assessment of land subsidence and associated faulting in Mexico City using InSAR. *Natural Hazards* 112(1):37–55. https://doi.org/10.1007/s11069-021-05171-0
- Herrera-García G, Ezquerro P, Tomás R, Béjar-Pizarro M, López-Vinielles J, Rossi M, Mateos RM, Carreón-Freyre D, et al. (2021) Mapping the global threat of land subsidence. *Science* 371(6524):34–36. https://doi.org/10.1126/science.abb8549
- Hoffmann J, Zebker HA, Galloway DL, Amelung F (2001) Seasonal subsidence and rebound in Las Vegas Valley, Nevada, observed by synthetic aperture radar interferometry. *Water Resources Research* 37(6):1551–1566. https://doi.org/10.1029/2000WR900404
- Minderhoud PSJ, Erkens G, Pham VH, Bui VT, Erban L, Kooi H, Stouthamer E (2017) Impacts of 25 years of groundwater extraction on subsidence in the Mekong delta, Vietnam. *Environmental Research Letters* 12:064006. https://doi.org/10.1088/1748-9326/aa7146
- Nguyen M, Lin Y-N, Tran QC, Ni C-F, Chan Y-C, Tseng K-H, Chang C-P (2022) Assessment of long-term ground subsidence and groundwater depletion in Hanoi, Vietnam. *Engineering Geology* 299:106555. https://doi.org/10.1016/j.enggeo.2022.106555
- Skempton AW, MacDonald DH (1956) The allowable settlements of buildings. *Proc. Institution of Civil Engineers* 5(6):727–768. https://doi.org/10.1680/ipeds.1956.12202
- Tomás R, Herrera G, Lopez-Sanchez JM, Vicente F, Cuenca A, Mallorquí JJ (2010) Study of the land subsidence in Orihuela City (SE Spain) using PSI data: distribution, evolution and correlation with conditioning and triggering factors. *Engineering Geology* 115(1–2):105–121. https://doi.org/10.1016/j.enggeo.2010.06.004
- Xu Y, van Tonder GJ (2001) Estimation of recharge using a revised CRD method. *Water SA* 27(3):341–343. https://doi.org/10.4314/wsa.v27i3.4977

**Trượt lở chậm, lượng mưa và dự báo phá huỷ**

- Bayer B, Simoni A, Mulas M, Corsini A, Schmidt D (2018) Deformation responses of slow moving landslides to seasonal rainfall in the Northern Apennines, measured by InSAR. *Geomorphology* 308:293–306. https://doi.org/10.1016/j.geomorph.2018.02.020
- Bekaert DPS, Handwerger AL, Agram P, Kirschbaum DB (2020) InSAR-based detection method for mapping and monitoring slow-moving landslides in remote regions with steep and mountainous terrain: an application to Nepal. *Remote Sensing of Environment* 249:111983. https://doi.org/10.1016/j.rse.2020.111983
- Bennett GL, Roering JJ, Mackey BH, Handwerger AL, Schmidt DA, Guillod BP (2016) Historic drought puts the brakes on earthflows in Northern California. *Geophysical Research Letters* 43(11):5725–5731. https://doi.org/10.1002/2016GL068378
- Caine N (1980) The rainfall intensity–duration control of shallow landslides and debris flows. *Geografiska Annaler A* 62(1–2):23–27. https://doi.org/10.1080/04353676.1980.11879996
- Crozier MJ (1999) Prediction of rainfall-triggered landslides: a test of the Antecedent Water Status Model. *Earth Surface Processes and Landforms* 24(9):825–833. https://doi.org/10.1002/(SICI)1096-9837(199908)24:9<825::AID-ESP14>3.0.CO;2-M
- Fukuzono T (1985) A method to predict the time of slope failure caused by rainfall using the inverse number of velocity of surface displacement. *J. Japan Landslide Society* 22(2):8–13. https://doi.org/10.3313/jls1964.22.2_8
- Glade T (2000) Applying probability determination to refine landslide-triggering rainfall thresholds using an empirical "Antecedent Daily Rainfall Model". *Pure and Applied Geophysics* 157(6–8):1059–1079. https://doi.org/10.1007/s000240050017 (Crossref chỉ ghi tên Glade; thường được trích dẫn cùng Crozier & Smith)
- Guzzetti F, Peruccacci S, Rossi M, Stark CP (2008) The rainfall intensity–duration control of shallow landslides and debris flows: an update. *Landslides* 5(1):3–17. https://doi.org/10.1007/s10346-007-0112-1
- Handwerger AL, Roering JJ, Schmidt DA (2013) Controls on the seasonal deformation of slow-moving landslides. *Earth and Planetary Science Letters* 377–378:239–247. https://doi.org/10.1016/j.epsl.2013.06.047
- Handwerger AL, Rempel AW, Skarbek RM, Roering JJ, Hilley GE (2016) Rate-weakening friction characterizes both slow sliding and catastrophic failure of landslides. *PNAS* 113(37):10281–10286. https://doi.org/10.1073/pnas.1607009113
- Handwerger AL, Huang M-H, Fielding EJ, Booth AM, Bürgmann R (2019) A shift from drought to extreme rainfall drives a stable landslide to catastrophic failure. *Scientific Reports* 9:1569. https://doi.org/10.1038/s41598-018-38300-0
- Hu X, Bürgmann R, Schulz WH, Fielding EJ (2020) Four-dimensional surface motions of the Slumgullion landslide and quantification of hydrometeorological forcing. *Nature Communications* 11:2792. https://doi.org/10.1038/s41467-020-16617-7
- Intrieri E, Raspini F, Fumagalli A, Lu P, Del Conte S, Farina P, Allievi J, Ferretti A, Casagli N (2018) The Maoxian landslide as seen from space: detecting precursors of failure with Sentinel-1 data. *Landslides* 15(1):123–133. https://doi.org/10.1007/s10346-017-0915-7
- Kirschbaum D, Stanley T (2018) Satellite-based assessment of rainfall-triggered landslide hazard for situational awareness. *Earth's Future* 6(3):505–523. https://doi.org/10.1002/2017EF000715
- Lacroix P, Handwerger AL, Bièvre G (2020) Life and death of slow-moving landslides. *Nature Reviews Earth & Environment* 1(8):404–419. https://doi.org/10.1038/s43017-020-0072-8
- Segoni S, Piciullo L, Gariano SL (2018) A review of the recent literature on rainfall thresholds for landslide occurrence. *Landslides* 15(8):1483–1501. https://doi.org/10.1007/s10346-018-0966-4
- Tomás R, Li Z, Liu P, Singleton A, Hoey T, Cheng X (2014) Spatiotemporal characteristics of the Huangtupo landslide in the Three Gorges region (China) constrained by radar interferometry. *Geophysical Journal International* 197(1):213–232. https://doi.org/10.1093/gji/ggu017
- Tran VA, Truong XQ, Nguyen DA, Longoni L, Yordanov V (2021) Landslides monitoring with time series of Sentinel-1 imagery in Yen Bai province, Vietnam. *ISPRS Archives* XLVI-4/W2-2021:197–203. https://doi.org/10.5194/isprs-archives-XLVI-4-W2-2021-197-2021
- Voight B (1988) A method for prediction of volcanic eruptions. *Nature* 332:125–130. https://doi.org/10.1038/332125a0
- Voight B (1989) A relation to describe rate-dependent material failure. *Science* 243(4888):200–203. https://doi.org/10.1126/science.243.4888.200

**Thống kê**

- Benjamini Y, Hochberg Y (1995) Controlling the false discovery rate: a practical and powerful approach to multiple testing. *J. Royal Statistical Society B* 57(1):289–300. https://doi.org/10.1111/j.2517-6161.1995.tb02031.x
- Benjamini Y, Yekutieli D (2001) The control of the false discovery rate in multiple testing under dependency. *Annals of Statistics* 29(4):1165–1188. https://doi.org/10.1214/aos/1013699998
- Ebisuzaki W (1997) A method to estimate the statistical significance of a correlation when the data are serially correlated. *Journal of Climate* 10(9):2147–2153. https://doi.org/10.1175/1520-0442(1997)010<2147:AMTETS>2.0.CO;2
- Knijnenburg TA, Wessels LFA, Reinders MJT, Shmulevich I (2009) Fewer permutations, more accurate P-values. *Bioinformatics* 25(12):i161–i168. https://doi.org/10.1093/bioinformatics/btp211
- Wilks DS (2016) "The stippling shows statistically significant grid points": how research results are routinely overstated and overinterpreted, and what to do about it. *Bulletin of the American Meteorological Society* 97(12):2263–2273. https://doi.org/10.1175/BAMS-D-15-00267.1

**Dữ liệu và yếu tố gây nhiễu**

- Fornaro G, Reale D, Verde S (2013) Bridge thermal dilation monitoring with millimeter sensitivity via multidimensional SAR imaging. *IEEE Geoscience and Remote Sensing Letters* 10(4):677–681. https://doi.org/10.1109/LGRS.2012.2218214
- Funk C, Peterson P, Landsfeld M, Pedreros D, Verdin J, Shukla S, Husak G, Rowland J, Harrison L, Hoell A, Michaelsen J (2015) The climate hazards infrared precipitation with stations — a new environmental record for monitoring extremes. *Scientific Data* 2:150066. https://doi.org/10.1038/sdata.2015.66
- Funk C, Peterson P, Harrison L, Saldivar R, Landsfeld M, Pedreros D, Shukla S, Fink A, et al. (2026) The Climate Hazards Center Infrared Precipitation with Stations, Version 3. *Scientific Data* 13:718. https://doi.org/10.1038/s41597-026-07096-4
- Hawker L, Uhe P, Paulo L, Sosa J, Savage J, Sampson C, Neal J (2022) A 30 m global map of elevation with forests and buildings removed. *Environmental Research Letters* 17:024016. https://doi.org/10.1088/1748-9326/ac4d4f
- Hersbach H, Bell B, Berrisford P, et al. (2020) The ERA5 global reanalysis. *Quarterly Journal of the Royal Meteorological Society* 146(730):1999–2049. https://doi.org/10.1002/qj.3803
- Huffman GJ, Bolvin DT, Braithwaite D, Hsu K-L, Joyce RJ, Kidd C, Nelkin EJ, Sorooshian S, Stocker EF, Tan J, Wolff DB, Xie P (2020) Integrated Multi-satellite Retrievals for the Global Precipitation Measurement (GPM) mission (IMERG). In: *Satellite Precipitation Measurement*, Advances in Global Change Research 67:343–353. https://doi.org/10.1007/978-3-030-24568-9_19
- Huffman GJ, Stocker EF, Bolvin DT, Nelkin EJ, Tan J (2023) GPM IMERG Final Precipitation L3 1 day 0.1° × 0.1° V07 (GPM_3IMERGDF). NASA GES DISC. https://doi.org/10.5067/GPM/IMERGDF/DAY/07
- Zippenfenig P (2024) Open-Meteo.com Weather API. Zenodo. https://doi.org/10.5281/zenodo.7970649

**Cần đọc toàn văn trước khi trích dẫn bất kỳ con số nào từ các nguồn sau:** quy tắc ma trận của Ciampalini et al.
(2016), ngưỡng gradient của Cigna & Tapete (2021), phương trình I–D của Guzzetti et al. (2008) và các trang tương ứng
của Bjerrum (1963). v1 không phụ thuộc vào con số nào trong số này.
