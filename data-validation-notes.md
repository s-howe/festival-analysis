# Data validation notes

Problems and fix ideas from a quick data validation.

## Festivals

Queen's yard summer party RA slug is promoters/99652 - needs title filter for "Queen's Yard Summer Party"
Doel festival RA slug is promoters/60724 - but this promoter also does Paradise City Festival so we need to split those somehow

|    |         festival_id | name               | notes                                           |
|---:|--------------------:|:-------------------|:------------------------------------------------|
|  1 | 3770262822180965878 | Stone Techno       | Single event here: https://ra.co/events/2244322 |
|  4 |   41474036776617358 | RIT/MO             | Single event here: https://ra.co/events/2322913 |
|  5 | 2245507121022757197 | Outwards           | Single event here: https://ra.co/events/2375273 |
|  7 | 5388978393463337345 | Vinculum           | Single event here: https://ra.co/events/2314934 |
|  9 | 1559338391378215778 | Bosburcht          | Single event here: https://ra.co/events/2099196 |
| 15 | 5968717876193840958 | Schall Im Schilf   | Single event here: https://ra.co/events/2127478 |
| 16 | 2544849023763392945 | Ribela Love Nature | Single event here: https://ra.co/events/1929415 |
| 17 | 9208427076163804902 | Surf Punat         | Single event here: https://ra.co/events/2350926 |
| 19 | 6998882899710125852 | Iberia Eclipse     | Single event here: https://ra.co/events/2339675 |
| 26 | 4171560534795669918 | Merci Beaucoup     | Single event here: https://ra.co/events/2132089 |
| 40 | 5812255783824147235 | Wild Weide         | seems to be clubs/271207                        |
| 45 | 3523969401856325801 | Funk In The Forest | Promoter page: promoters/159862                 |
| 52 | 5457462565715645084 | Miceli             | Single event here.                              | 

## Artists

Did we save artist biographies anywhere?

## Artist genres

Seems to only contain 10 records for Jane Fitz.

## Festival instances

Lots of festival instances only have a few artists - be suspicious of any with less than 20 artists. Maybe check RA event ID really goes to the festival page?
