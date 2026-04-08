"""GraphQL query strings for the Resident Advisor API.

These are reverse-engineered from the public ra.co site and the
djb-gt/resident-advisor-events-scraper project. The schema is undocumented
and may change without warning.
"""

GET_EVENT_LISTINGS = """
query GET_EVENT_LISTINGS(
  $filters: FilterInputDtoInput
  $filterOptions: FilterOptionsInputDtoInput
  $page: Int
  $pageSize: Int
) {
  eventListings(
    filters: $filters
    filterOptions: $filterOptions
    pageSize: $pageSize
    page: $page
  ) {
    data {
      id
      listingDate
      event {
        id
        title
        date
        startTime
        endTime
        contentUrl
        venue {
          id
          name
          contentUrl
          live
          area {
            id
            name
            country {
              id
              name
            }
          }
        }
        artists {
          id
          name
        }
      }
    }
    totalResults
  }
}
"""

GET_EVENT_DETAIL = """
query GET_EVENT_DETAIL($id: ID!) {
  event(id: $id) {
    id
    title
    date
    startTime
    endTime
    contentUrl
    venue {
      id
      name
      area {
        id
        name
        country { id name }
      }
    }
    artists {
      id
      name
    }
    pick { blurb }
  }
}
"""

GET_PROMOTER_EVENTS = """
query GET_PROMOTER_EVENTS($id: ID!, $year: Int, $limit: Int) {
  promoter(id: $id) {
    id
    name
    events(type: ARCHIVE, year: $year, limit: $limit) {
      id
      title
      date
      startTime
      endTime
      contentUrl
      venue {
        id
        name
        contentUrl
        area {
          id
          name
          country { id name }
        }
      }
      artists { id name }
    }
  }
}
"""

GET_VENUE_EVENTS = """
query GET_VENUE_EVENTS($id: ID!, $year: Int, $limit: Int) {
  venue(id: $id) {
    id
    name
    events(type: ARCHIVE, year: $year, limit: $limit) {
      id
      title
      date
      startTime
      endTime
      contentUrl
      venue {
        id
        name
        contentUrl
        area {
          id
          name
          country { id name }
        }
      }
      artists { id name }
    }
  }
}
"""

_ARTIST_FIELDS = """
  id
  name
  country { name }
  area { name }
  status
  instagram
  soundcloud
  twitter
"""


def build_artist_batch_query(ids: list[str]) -> str:
    """Build a GraphQL query that fetches up to `len(ids)` artists in one request."""
    aliases = "\n".join(
        f'  a{i}: artist(id: "{aid}") {{{_ARTIST_FIELDS}  }}'
        for i, aid in enumerate(ids)
    )
    return f"query GET_ARTIST_BATCH {{\n{aliases}\n}}"


SEARCH = """
query SEARCH($searchTerm: String!, $indices: [IndexType!]) {
  search(searchTerm: $searchTerm, indices: $indices, limit: 5) {
    searchType
    id
    value
    contentUrl
  }
}
"""
