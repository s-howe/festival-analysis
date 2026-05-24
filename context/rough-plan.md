# Festival analysis

Aim is to do a wide analysis of festival DJ bookings across Europe and beyond.

## Data collection

1. Collect names of all interesting festivals
2. Scrape RA lineups for each festival, saving date, artist names, location
3. Create relational db of artists, festivals, festival instances, lineups

### Resident Advisor API

Apparently RA has a GraphQL API which is fairly undocumented. Resources:
- https://stackoverflow.com/questions/34182163/how-to-get-residentadvisor-api-functional
- https://www.residentadvisor.net/api/dj.asmx?op=getartist
- https://github.com/djb-gt/resident-advisor-events-scraper

### Edge cases
- Some artists might have aliases - this is fine, treat as separate artists for now
- Some artists might be spelled differently across event lineups, try and unify them
- Some artists might not have links or RA pages, try and resolve these
- b2b listings should be split into substituent DJs

## Data enrichment

- Festival size, country, time of year, number of instances, age
- Artist age, gender, country of origin, race(?), instagram followers, years active, producer or not, live show or DJ
- Festival instance scores:
    - Uniqueness (1 - Jaccard similarity index)
    - Gender diversity
    - Racial diversity

## Exploratory data analysis

- Plot distributions
- Festival count over time
- Big hitters over time - stacked area chart of festivals played per year by each artist
- Seasonal distribution of festivals
- Matrix of festival country vs artist country
- Signature artists per festival

## Deep dives

- Tipping point - is there a festival where once an artist plays there, they tend to get booked everywhere?
- Do artists generally follow a rise and fall? Playing at smaller festivals first, then larger, then smaller again?
- Stickyness - do certain artists stay at the top, while some rise up and burn out quickly?
- Local heroes - which festivals book the highest share of artists from their country? Which book the least?
- Cultural exporters - which countries churn out the biggest hitting artists?
- Freshness - which festivals have a high returning artist count vs fresh faces?
- Taste makers - which festivals tend to book emerging artists, which only book big hitters?

## Network graphs

- Festival graph - edge weight is similarity to other festivals (Jaccard index)
- Artist graph - edge weight is number of shared lineups
- Bi-graph - artists and festivals together
- Year-by-year evolution of the networks (Javascript scrubber)

## Future ideas (later projects)

- Causal impact on diversity - did 2020's BLM and other diversity focuses cause an increase in diversity in festival bookings? By how much? Was this focused on certain types of festivals and not others?
- Festival vs club appearances - who only plays festivals/only plays clubs
- Artists by genre - capture artist bios and extract genres, use to group festivals by main genres
- Predictive modeling - can we accurately predict the lineup of next year’s Dekmantel based on artist features?
