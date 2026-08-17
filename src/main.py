from linking import link_all_notices
from transferToNeo4j import transfer_links_to_neo4j

if __name__ == "__main__":
    link_all_notices()

    transfer_links_to_neo4j()
