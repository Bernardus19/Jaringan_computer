## Cara menjalankan
Karena pakai raw socket, program harus dijalankan sebagai administrator/root.
Windows: buka VS Code atau terminal dengan **Run as administrator**, lalu:
```
python labtest.py google.com
```
Kalau nama host nggak diisi, default-nya ping ke `127.0.0.1`. Ketik nama domainnya aja, tanpa `https://`.
---

# BAB I PENDAHULUAN DAN DASAR TEORI

## 1.1 Latar Belakang

Ping itu salah satu tool jaringan yang paling sering dipakai. Fungsinya simpel: ngecek apakah suatu host bisa dijangkau lewat jaringan IP, sekaligus ngukur seberapa lama paket bolak-balik ke host itu (latency). Kalau lagi internet lemot atau suatu website nggak kebuka, biasanya hal pertama yang dicoba ya ping.

Di balik itu, ping sebenarnya cuma memanfaatkan dua jenis pesan dari protokol ICMP (Internet Control Message Protocol): **echo request** yang dikirim ke tujuan, dan **echo reply** yang dibalas oleh tujuan. Lab ini minta kita bikin sendiri aplikasi ping versi sederhana pakai Python dan raw socket, jadi kita bisa lihat langsung isi header ICMP dan gimana cara ngitung waktu bolak-baliknya (round-trip time/RTT).

## 1.2 Tujuan

- Memahami cara kerja ICMP, khususnya pesan echo request dan echo reply.
- Membuat aplikasi ping sendiri di Python yang mengirim echo request tiap kira-kira 1 detik dan menunggu balasan maksimal 1 detik.
- Menghitung RTT tiap paket, lalu merangkum hasilnya (RTT minimum, rata-rata, maksimum, dan persentase packet loss).
- Membaca kode error ICMP seperti Destination Unreachable, tidak cuma mendeteksi timeout.
- Menguji aplikasi ke beberapa host di lokasi yang berbeda dan menganalisis hasilnya.

## 1.3 Dasar Teori

### 1.3.1 ICMP

ICMP dipakai oleh host dan router buat saling kirim informasi kontrol dan pesan error, misal kalau tujuan nggak bisa dijangkau atau TTL paket habis di tengah jalan. ICMP bekerja di lapisan jaringan (network layer) dan pesannya dibungkus di dalam paket IP, dengan nomor protokol 1. Karena itu paket yang kita terima di program selalu diawali header IP dulu, baru header ICMP di belakangnya.

### 1.3.2 Format Header ICMP

Header ICMP untuk echo request/reply panjangnya 8 byte, dengan susunan sebagai berikut.

| Field | Ukuran | Keterangan |
|-------|:------:|------------|
| Type | 8 bit | Jenis pesan. 8 = echo request, 0 = echo reply, 3 = destination unreachable, 11 = time exceeded. |
| Code | 8 bit | Sub-jenis dari Type. Untuk echo, nilainya 0. |
| Checksum | 16 bit | Pengecekan error, dihitung dari header + data dengan field checksum diisi 0 dulu. |
| Identifier (ID) | 16 bit | Penanda yang harus dikembalikan di echo reply, dipakai untuk mencocokkan balasan dengan permintaan. |
| Sequence | 16 bit | Nomor urut paket, juga dikembalikan di echo reply. |

Setelah header, ada bagian data (payload). Aturannya, data yang diterima host tujuan di echo request harus dikembalikan utuh di echo reply. Trik ini yang kita pakai: payload diisi timestamp waktu kirim, jadi waktu balasan datang tinggal dikurangkan untuk dapat RTT.

### 1.3.3 Echo Request, Echo Reply, dan Pesan Error

Echo request (type 8, code 0) dikirim oleh pengirim, dan setiap host wajib membalas dengan echo reply (type 0, code 0). Kalau tujuan atau router di tengah jalan nggak bisa meneruskan paket, mereka bisa mengirim pesan error balik. Dua yang relevan untuk lab ini:

- **Destination Unreachable (type 3).** Code 0 berarti jaringan tujuan tidak terjangkau, code 1 berarti host tujuan tidak terjangkau, dan seterusnya.
- **Time Exceeded (type 11).** Muncul kalau TTL paket sudah habis (jadi 0) sebelum sampai tujuan.

Pesan error ini membawa kembali header IP asli dan 8 byte pertama dari ICMP yang kita kirim, jadi program bisa mengecek apakah error tersebut benar-benar untuk ping milik kita (lewat ID).

### 1.3.4 RTT dan TTL

**RTT (round-trip time)** adalah waktu dari paket dikirim sampai balasannya diterima, biasanya dalam milidetik. **TTL (time to live)** adalah angka di header IP yang dikurangi 1 tiap melewati router. Kalau sudah 0, paket dibuang. Nilai awal TTL beda-beda tergantung sistem operasi server (umumnya 64, 128, atau 255), jadi dari TTL yang kita terima kita bisa memperkirakan kira-kira berapa router yang dilewati.

### 1.3.5 Raw Socket

Socket biasa (TCP/UDP) menyembunyikan header protokol dari programmer. Untuk ICMP kita butuh raw socket (`SOCK_RAW`) supaya bisa menyusun header sendiri dan membaca paket mentah yang datang, termasuk header IP-nya. Konsekuensinya, program harus dijalankan dengan hak akses administrator/root, kalau nggak akan muncul `PermissionError`.

---

# BAB II IMPLEMENTASI PROGRAM

## 2.1 Lingkungan Pengerjaan

- Bahasa: Python 3.13
- Editor: Visual Studio Code, terminal PowerShell dijalankan sebagai Administrator (Windows)
- Nama file program: `labtest.py`

Terminal harus dibuka sebagai administrator karena program memakai raw socket.

## 2.2 Alur Program

Program terdiri dari beberapa fungsi yang dipanggil berurutan:

1. `ping(host)` menerjemahkan nama host jadi alamat IP (`gethostbyname`), lalu mengulang pengiriman ping sebanyak 10 kali dengan jeda 1 detik.
2. `doOnePing()` membuat raw socket ICMP, memanggil `sendOnePing()` lalu `receiveOnePing()`, dan menutup socket.
3. `sendOnePing()` menyusun paket (header ICMP + timestamp), menghitung checksum, lalu mengirimnya.
4. `receiveOnePing()` menunggu balasan memakai `select` dengan batas waktu 1 detik, lalu membaca isi paket yang datang.
5. Setelah semua ping selesai, `ping()` menampilkan statistik: jumlah paket, packet loss, dan RTT min/avg/max.

## 2.3 Pengiriman Paket (sendOnePing)

Header ICMP disusun dengan `struct.pack`. Mula-mula checksum diisi 0, lalu checksum dihitung dari header + data, dan header disusun ulang dengan checksum yang benar. Payload-nya adalah `time.time()` yang dipack sebagai 8 byte (`d`).

```python
header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, myChecksum, ID, 1)
data = struct.pack("d", time.time())
myChecksum = checksum(header + data)
header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, myChecksum, ID, 1)
packet = header + data
mySocket.sendto(packet, (destAddr, 1))
```

Total ukuran ICMP yang dikirim 16 byte (8 byte header + 8 byte timestamp). Ini sesuai dengan keluaran `bytes=16` di hasil pengujian nanti.

## 2.4 Penyesuaian dari Skeleton

Skeleton yang diberikan ditulis untuk Python 2, jadi ada beberapa bagian yang harus disesuaikan supaya jalan di Python 3:

- Fungsi `checksum` aslinya memanggil `ord()` pada string, dan `sendOnePing` memanggil `checksum(str(header + data))`. Di Python 3, `str()` pada bytes malah menghasilkan teks `b'...'`, jadi checksum jadi salah. Di versi ini `checksum` langsung menerima bytes.
- Header dipack dengan format `"!BBHHH"`. Tanda `!` artinya network byte order (big-endian), jadi nggak perlu lagi `htons`. Sequence juga dibuat unsigned (`H`) biar konsisten.
- Panjang header IP dibaca dari field IHL, bukan di-hardcode 20 byte, karena header IP bisa lebih panjang kalau ada option.

```python
def checksum(data):
    csum = 0
    countTo = (len(data) // 2) * 2
    for count in range(0, countTo, 2):
        csum += (data[count] << 8) + data[count + 1]
    if countTo < len(data):
        csum += data[-1] << 8
    csum = (csum >> 16) + (csum & 0xFFFF)
    csum += csum >> 16
    return ~csum & 0xFFFF
```

## 2.5 Bagian Fill in (receiveOnePing)

Bagian yang diisi adalah pembacaan paket balasan. Paket yang diterima berisi header IP lalu header ICMP. Langkahnya: hitung panjang header IP dari IHL, ambil 8 byte header ICMP setelahnya, lalu unpack field-fieldnya.

```python
ipHeaderLen = (recPacket[0] & 0x0F) * 4
ttl = recPacket[8]

icmpHeader = recPacket[ipHeaderLen:ipHeaderLen + 8]
icmpType, code, recvChecksum, packetID, sequence = \
    struct.unpack("!BBHHH", icmpHeader)

if icmpType == 0 and packetID == ID:
    timeSent = struct.unpack("d",
        recPacket[ipHeaderLen + 8:ipHeaderLen + 16])[0]
    rtt = (timeReceived - timeSent) * 1000  # ms
    size = len(recPacket) - ipHeaderLen
    return rtt, "Reply from %s: bytes=%d time=%.2f ms TTL=%d" % (addr[0], size, rtt, ttl)
```

Paket dianggap balasan ping kita kalau type-nya 0 (echo reply) dan ID-nya sama dengan ID proses kita. Pengecekan ID ini penting karena raw socket menerima semua paket ICMP yang masuk ke komputer, termasuk balasan untuk proses lain. TTL diambil dari byte ke-8 header IP (`recPacket[8]`).

## 2.6 Latihan Opsional

### 2.6.1 Statistik RTT dan Packet Loss

Tiap ping yang berhasil, RTT-nya disimpan ke sebuah list. Di akhir, program menghitung packet loss dari jumlah paket yang tidak dibalas, dan RTT minimum, rata-rata, serta maksimum dari list tadi.

```python
loss = (sent - len(rtts)) / sent * 100
print("%d packets transmitted, %d received, %.1f%% packet loss" % (sent, len(rtts), loss))
if rtts:
    print("rtt min/avg/max = %.2f/%.2f/%.2f ms" % (min(rtts), sum(rtts)/len(rtts), max(rtts)))
```

### 2.6.2 Membaca Kode Error ICMP

Selain echo reply, program juga mengenali pesan type 3 (Destination Unreachable) dengan kode 0 sampai 5, dan type 11 (Time Exceeded). Sebelum ditampilkan, ID di dalam paket error dicek dulu. ID itu ada di dalam ICMP asli yang dibawa balik oleh pesan error, jadi error dari proses lain tidak ikut tercampur.

```python
if icmpType == 3 and getInnerID(recPacket, ipHeaderLen) == ID:
    msg = UNREACHABLE_CODES.get(code, "Destination Unreachable (code %d)" % code)
    return None, "Reply from %s: %s" % (addr[0], msg)

if icmpType == 11 and getInnerID(recPacket, ipHeaderLen) == ID:
    return None, "Reply from %s: Time to live exceeded" % addr[0]
```

Kode lengkap program ada di file [`labtest.py`](labtest.py).

---

# BAB III HASIL DAN ANALISIS

## 3.1 Skenario Pengujian

Program dijalankan dari terminal dengan perintah `python labtest.py <host>`. Tiap host dikirimi 10 paket echo request dengan jeda sekitar 1 detik dan timeout 1 detik per paket. Host yang diuji:

- `www.u-tokyo.ac.jp` (Universitas Tokyo, Jepang)
- `www.usyd.edu.au` (Universitas Sydney, Australia)
- `google.com`
- `www.ukdc.ac.id` (kampus sendiri, Indonesia)

## 3.2 Hasil Pengujian

### 3.2.1 google.com

![Hasil ping ke google.com](screenshots/google.png)

*Gambar 3.1 Hasil ping ke google.com*

Semua 10 paket dibalas (0% loss). RTT minimum 36,88 ms, rata-rata 64,28 ms, dan maksimum 149,93 ms. TTL yang diterima 103.

### 3.2.2 www.ukdc.ac.id

![Hasil ping ke www.ukdc.ac.id](screenshots/ukdc.png)

*Gambar 3.2 Hasil ping ke www.ukdc.ac.id*

Semua 10 paket dibalas (0% loss). RTT minimum 20,20 ms, rata-rata 37,86 ms, dan maksimum 102,91 ms. TTL yang diterima 55.

### 3.2.3 www.u-tokyo.ac.jp

![Hasil ping ke www.u-tokyo.ac.jp](screenshots/u-tokyo.png)

*Gambar 3.3 Hasil ping ke www.u-tokyo.ac.jp*

Alamat IP berhasil ditemukan (210.152.243.234), tapi semua paket berakhir `Request timed out`. Hasil akhirnya 10 paket terkirim, 0 diterima, packet loss 100%.

### 3.2.4 www.usyd.edu.au

![Hasil ping ke www.usyd.edu.au](screenshots/usyd-1.png)

*Gambar 3.4 Hasil ping ke www.usyd.edu.au*

![Percobaan ulang ke www.usyd.edu.au](screenshots/usyd-2.png)

*Gambar 3.5 Percobaan ulang ke www.usyd.edu.au*

Hasilnya sama, 10 paket terkirim dan 0 diterima (100% loss). Menariknya, alamat IP yang didapat berbeda di tiap percobaan: 54.253.135.10 di percobaan pertama dan 54.79.77.129 di percobaan kedua.

## 3.3 Ringkasan

| Host | IP | Kirim | Terima | Loss | RTT min/avg/max (ms) | TTL |
|------|----|:-----:|:------:|:----:|:--------------------:|:---:|
| www.u-tokyo.ac.jp | 210.152.243.234 | 10 | 0 | 100% | - | - |
| www.usyd.edu.au | 54.253.135.10 / 54.79.77.129 | 10 | 0 | 100% | - | - |
| google.com | 142.251.12.102 | 10 | 10 | 0% | 36,88 / 64,28 / 149,93 | 103 |
| www.ukdc.ac.id | 202.78.200.98 | 10 | 10 | 0% | 20,20 / 37,86 / 102,91 | 55 |

## 3.4 Analisis

### 3.4.1 Host yang membalas

Untuk `www.ukdc.ac.id`, RTT rata-ratanya paling kecil (37,86 ms). Masuk akal karena server dan komputer yang dipakai sama-sama di Indonesia, jadi jalurnya pendek. TTL-nya 55, dan karena nilai awal TTL yang umum adalah 64, itu artinya paket kira-kira melewati sekitar 9 router.

Untuk `google.com`, TTL 103 kemungkinan berasal dari nilai awal 128, jadi sekitar 25 router dilewati. RTT rata-ratanya 64,28 ms. Kalau server Google yang dituju benar-benar ada di Amerika, RTT dari Indonesia biasanya jauh lebih besar dari ini, jadi dugaan kami balasan datang dari server Google yang lebih dekat (edge/CDN). Tapi ini cuma dugaan dari angka RTT, karena ping sendiri nggak memberi tahu lokasi server.

Di dua host ini RTT antar paket cukup naik-turun, misal di google.com dari 36,88 ms sampai 149,93 ms, dan di ukdc dari 20,20 ms sampai 102,91 ms. Variasi seperti ini wajar karena kondisi jaringan di tiap paket beda-beda (antrean di router, beban jaringan, dan lain-lain).

### 3.4.2 Host yang tidak membalas

`www.u-tokyo.ac.jp` dan `www.usyd.edu.au` sama-sama timeout 100%. Kalau melihat hasil dua host lain, kecil kemungkinan masalahnya ada di program: IP berhasil ditemukan, paket terkirim tanpa error, dan program yang sama bisa menerima balasan dari google.com dan ukdc.ac.id. Dugaan paling masuk akal adalah server-server itu (atau firewall di depannya) memang menolak atau membuang paket ICMP echo request.

Untuk usyd.edu.au, ada petunjuk tambahan: alamat IP-nya berganti-ganti antar percobaan, dan kedua alamat itu kelihatannya berasal dari layanan cloud. Konfigurasi bawaan layanan cloud biasanya tidak mengizinkan ICMP masuk. Perlu dicatat ini juga masih dugaan, karena kami tidak bisa memeriksa konfigurasi server mereka.

Satu hal penting dari sini: timeout nggak otomatis berarti server mati. Website tetap bisa hidup walaupun ICMP-nya ditutup, jadi hasil ping yang gagal harus dibaca hati-hati.

### 3.4.3 Catatan Pengujian

Pengujian cuma 10 paket per host, jadi angka rata-rata dan maksimumnya bisa berubah kalau dites di waktu lain atau dengan paket lebih banyak. Selain itu, program belum mengubah nomor sequence untuk tiap paket (selalu 1), tapi karena tiap ping memakai socket baru dan dicocokkan lewat ID, ini tidak mengganggu hasil.

---

# BAB IV KESIMPULAN

## 4.1 Kesimpulan

1. Aplikasi ping berhasil dibuat di Python memakai raw socket ICMP. Program mengirim echo request, membaca header IP dan ICMP dari balasan, lalu menghitung RTT dari timestamp yang dititipkan di payload.
2. Skeleton lab perlu disesuaikan untuk Python 3, terutama di fungsi checksum (bytes, bukan string) dan pembacaan panjang header IP dari field IHL.
3. Dari empat host yang diuji, dua host membalas: `www.ukdc.ac.id` dengan RTT rata-rata 37,86 ms dan `google.com` dengan RTT rata-rata 64,28 ms, keduanya 0% packet loss. Dua host lain, `www.u-tokyo.ac.jp` dan `www.usyd.edu.au`, tidak membalas sama sekali (100% loss).
4. Timeout di dua host itu kemungkinan besar karena ICMP diblokir di sisi server atau firewall, bukan karena program salah. Jadi timeout tidak bisa langsung diartikan server mati.
5. Latihan opsional berhasil dikerjakan: program menampilkan statistik RTT min/avg/max beserta packet loss, dan bisa mengenali pesan Destination Unreachable dan Time Exceeded.
