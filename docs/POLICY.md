# hibrit-trader Politika Dokumani

(tarih: 2026-06-22. Rakamlar in-sample snapshot, ~112 trade paper. Cok-rejim onayi bekliyor.)

## Mevcut Durum

net -%8.7, PF 0.98, kronik basa-bas-alti, paper.

## A) Kaybeden Kisimlar

- flash -1525 (baskin kanama, gap-down, cikisla kesilemez)
- friction ~%98 (TODO: dolar olarak olc, flash -1525 ile sirala, #1 kaldirac olabilir)
- <2dk churn -744 (hizli giris-cikis, round-trip maliyeti edge'i yiyor)

## B) Olu Agirlik

- giris alfasi r~0
- yuksek-skor -0.291 (NOT: r~0 degil, hafif anti-predictive, skor aktif zararli olabilir, kesif gerek)
- scratch-grace (:228) -53

## C) Calisan / Dokunma

- cikis motoru +2018 (gercek edge, tartisma disi)
- C1 (genesis yari-boyut)
- guvenlik filtresi (holder vb sert filtre)

## 6 Ilke

1. Giris-alfasini dondur.
2. Scale-in: KOSULLU. Exit-log runner-zaman-profili runner'larin yavas oldugunu dogrularsa uygulanir, yoksa hayir. Su an hipotez, doktrin degil.
3. Friction-kesimi: az ve uzun-tutulan trade, churn'u kes.
4. Ucuz stop'lar additif degil, RESIDUAL etkiyi olc (flash gap cogu cikisi deler).
5. Cikisa dokunma.
6. Tek-degisken + cok-rejim. Durust tavan PF 1.0-1.3.

## KILL-CRITERION

- Levereler sonrasi PF < 1.0 ise CANLI YOK.
- Canli bari: cok-rejim PF > 1.1 istikrarli (en az N trade, M ayri rejim uzerinde; TODO: N ve M tanimla) VE friction modellenmis.

## Disiplin

Forward gercektir, in-sample yon verir. Kucuk ornekleme guvenme. Kasa gecikmeli yer gercegi. Her degisiklik tek basina forward'da dogrulanir.
