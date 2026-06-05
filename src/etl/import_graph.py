from neo4j import GraphDatabase
import shutil
import os
import time


def run(session, query, description=""):
    start = time.time()
    session.run(query)
    duration = time.time() - start
    print(f"  ✓ {description} ({duration:.1f}s)")


def import_graph(uri, password, csv_dir, import_dir):
    print("=== Copie des CSV ===")
    for f in os.listdir(csv_dir):
        if f.endswith(".csv"):
            shutil.copy(os.path.join(csv_dir, f), import_dir)
            print(f"  Copié : {f}")

    driver = GraphDatabase.driver(uri, auth=("neo4j", password))

    with driver.session() as session:

        print("\n=== Phase 1 — Contraintes ===")

        run(session, """
            CREATE CONSTRAINT update_revision_id IF NOT EXISTS
            FOR (u:Update) REQUIRE u.revision_id IS UNIQUE
        """, "Update.revision_id")

        run(session, """
            CREATE CONSTRAINT category_key IF NOT EXISTS
            FOR (c:Category) REQUIRE c.category_key IS UNIQUE
        """, "Category.category_key")

        run(session, """
            CREATE CONSTRAINT kb_article_id IF NOT EXISTS
            FOR (k:KBArticle) REQUIRE k.kb_article_id IS UNIQUE
        """, "KBArticle.kb_article_id")

        run(session, """
            CREATE CONSTRAINT cve_id IF NOT EXISTS
            FOR (c:CVE) REQUIRE c.cve_id IS UNIQUE
        """, "CVE.cve_id")

        run(session, """
            CREATE CONSTRAINT eula_digest IF NOT EXISTS
            FOR (e:Eula) REQUIRE e.digest IS UNIQUE
        """, "Eula.digest")

        run(session, """
            CREATE CONSTRAINT behavior_id IF NOT EXISTS
            FOR (b:UpdateBehavior) REQUIRE b.behavior_id IS UNIQUE
        """, "UpdateBehavior.behavior_id")

        run(session, """
            CREATE CONSTRAINT language_code IF NOT EXISTS
            FOR (l:Language) REQUIRE l.language_code IS UNIQUE
        """, "Language.language_code")

        run(session, """
            CREATE INDEX update_id IF NOT EXISTS
            FOR (u:Update) ON (u.update_id)
        """, "Index Update.update_id")

        print("\n=== Phase 2 — Noeuds ===")

        run(session, """
            LOAD CSV WITH HEADERS FROM 'file:///languages.csv' AS row
            MERGE (:Language {language_code: row.language_code})
        """, "Language")

        run(session, """
            LOAD CSV WITH HEADERS FROM 'file:///kb_articles.csv' AS row
            MERGE (k:KBArticle {kb_article_id: row.kb_article_id})
            SET k.bulletin_id = CASE WHEN row.bulletin_id <> '' THEN row.bulletin_id ELSE null END
        """, "KBArticle")

        run(session, """
            LOAD CSV WITH HEADERS FROM 'file:///cves.csv' AS row
            MERGE (:CVE {cve_id: row.cve_id})
        """, "CVE")

        run(session, """
            LOAD CSV WITH HEADERS FROM 'file:///eulas.csv' AS row
            MERGE (e:Eula {digest: row.digest})
            SET e.file_name     = CASE WHEN row.file_name    <> '' THEN row.file_name    ELSE null END,
                e.size          = CASE WHEN row.size          <> '' THEN toInteger(row.size) ELSE null END,
                e.language      = CASE WHEN row.language      <> '' THEN row.language      ELSE null END,
                e.sha256_digest = CASE WHEN row.sha256_digest <> '' THEN row.sha256_digest ELSE null END
        """, "Eula")

        run(session, """
            LOAD CSV WITH HEADERS FROM 'file:///behaviors.csv' AS row
            MERGE (b:UpdateBehavior {behavior_id: row.behavior_id})
            SET b.handler                       = CASE WHEN row.handler                       <> '' THEN row.handler                       ELSE null END,
                b.reboot_behavior               = CASE WHEN row.reboot_behavior               <> '' THEN row.reboot_behavior               ELSE null END,
                b.can_request_user_input        = CASE WHEN row.can_request_user_input        <> '' THEN row.can_request_user_input        ELSE null END,
                b.impact                        = CASE WHEN row.impact                        <> '' THEN row.impact                        ELSE null END,
                b.requires_network_connectivity = CASE WHEN row.requires_network_connectivity <> '' THEN row.requires_network_connectivity ELSE null END,
                b.patching_type                 = CASE WHEN row.patching_type                 <> '' THEN row.patching_type                 ELSE null END,
                b.reboot_behavior_uninstall     = CASE WHEN row.reboot_behavior_uninstall     <> '' THEN row.reboot_behavior_uninstall     ELSE null END,
                b.permanence                    = CASE WHEN row.permanence                    <> '' THEN row.permanence                    ELSE null END,
                b.self_update                   = CASE WHEN row.self_update                   <> '' THEN row.self_update                   ELSE null END
        """, "UpdateBehavior")

        run(session, """
            LOAD CSV WITH HEADERS FROM 'file:///categories.csv' AS row
            MERGE (c:Category {category_key: row.category_key})
            SET c.company                  = CASE WHEN row.company                  <> '' THEN row.company                  ELSE null END,
                c.company_id               = CASE WHEN row.company_id               <> '' THEN row.company_id               ELSE null END,
                c.product_family           = CASE WHEN row.product_family           <> '' THEN row.product_family           ELSE null END,
                c.product_family_id        = CASE WHEN row.product_family_id        <> '' THEN row.product_family_id        ELSE null END,
                c.product                  = CASE WHEN row.product                  <> '' THEN row.product                  ELSE null END,
                c.product_id               = CASE WHEN row.product_id               <> '' THEN row.product_id               ELSE null END,
                c.update_classification    = CASE WHEN row.update_classification    <> '' THEN row.update_classification    ELSE null END,
                c.update_classification_id = CASE WHEN row.update_classification_id <> '' THEN row.update_classification_id ELSE null END
        """, "Category")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///updates.csv' AS row
            WITH row WHERE row.revision_id IS NOT NULL AND row.revision_id <> ''
            MERGE (u:Update {revision_id: row.revision_id})
            SET u.update_id                   = row.update_id,
                u.revision_number             = toInteger(row.revision_number),
                u.creation_date               = row.creation_date,
                u.default_language            = CASE WHEN row.default_language            <> '' THEN row.default_language            ELSE null END,
                u.is_leaf                     = CASE WHEN row.is_leaf                     <> '' THEN (row.is_leaf = 'true')          ELSE null END,
                u.is_bundle                   = CASE WHEN row.is_bundle                   <> '' THEN (row.is_bundle = 'true')        ELSE null END,
                u.is_software                 = CASE WHEN row.is_software                 <> '' THEN (row.is_software = 'true')      ELSE null END,
                u.deployment_action           = CASE WHEN row.deployment_action           <> '' THEN row.deployment_action           ELSE null END,
                u.title                       = CASE WHEN row.title                       <> '' THEN row.title                       ELSE null END,
                u.description                 = CASE WHEN row.description                 <> '' THEN row.description                 ELSE null END,
                u.more_info_url               = CASE WHEN row.more_info_url               <> '' THEN row.more_info_url               ELSE null END,
                u.support_url                 = CASE WHEN row.support_url                 <> '' THEN row.support_url                 ELSE null END,
                u.uninstall_notes             = CASE WHEN row.uninstall_notes             <> '' THEN row.uninstall_notes             ELSE null END,
                u.msr_severity                = CASE WHEN row.msr_severity                <> '' THEN row.msr_severity                ELSE null END,
                u.browse_only                 = CASE WHEN row.browse_only                 <> '' THEN (row.browse_only = 'true')      ELSE null END,
                u.is_beta                     = CASE WHEN row.is_beta                     <> '' THEN (row.is_beta = 'true')          ELSE null END,
                u.release_version             = CASE WHEN row.release_version             <> '' THEN row.release_version             ELSE null END,
                u.release_revision            = CASE WHEN row.release_revision            <> '' THEN toInteger(row.release_revision) ELSE null END,
                u.min_download_size           = CASE WHEN row.min_download_size           <> '' THEN toInteger(row.min_download_size) ELSE null END,
                u.max_download_size           = CASE WHEN row.max_download_size           <> '' THEN toInteger(row.max_download_size) ELSE null END,
                u.recommended_hard_disk_space = CASE WHEN row.recommended_hard_disk_space <> '' THEN toInteger(row.recommended_hard_disk_space) ELSE null END,
                u.recommended_memory          = CASE WHEN row.recommended_memory          <> '' THEN toInteger(row.recommended_memory) ELSE null END,
                u.recommended_cpu_speed       = CASE WHEN row.recommended_cpu_speed       <> '' THEN toInteger(row.recommended_cpu_speed) ELSE null END,
                u.can_source_be_required      = CASE WHEN row.can_source_be_required      <> '' THEN (row.can_source_be_required = 'true') ELSE null END,
                u.product_code                = CASE WHEN row.product_code                <> '' THEN row.product_code                ELSE null END,
                u.update_type                 = CASE WHEN row.update_type                 <> '' THEN row.update_type                 ELSE null END,
                u.explicitly_deployable       = CASE WHEN row.explicitly_deployable       <> '' THEN (row.explicitly_deployable = 'true') ELSE null END,
                u.completely_offline_capable  = CASE WHEN row.completely_offline_capable  <> '' THEN (row.completely_offline_capable = 'true') ELSE null END,
                u.inf                         = CASE WHEN row.inf                         <> '' THEN row.inf                         ELSE null END,
                u.auto_select_on_websites     = CASE WHEN row.auto_select_on_websites     <> '' THEN (row.auto_select_on_websites = 'true') ELSE null END
            } IN TRANSACTIONS OF 5000 ROWS
        """, "Update")

        print("\n=== Phase 3 — Relations ===")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///rel_has_behavior.csv' AS row
            MATCH (u:Update {revision_id: row.revision_id})
            MATCH (b:UpdateBehavior {behavior_id: row.behavior_id})
            MERGE (u)-[:HAS_BEHAVIOR]->(b)
            } IN TRANSACTIONS OF 5000 ROWS
        """, "HAS_BEHAVIOR")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///rel_belongs_to.csv' AS row
            MATCH (u:Update {revision_id: row.revision_id})
            MATCH (c:Category {category_key: row.category_key})
            MERGE (u)-[:BELONGS_TO {complete: (row.complete = 'True')}]->(c)
            } IN TRANSACTIONS OF 5000 ROWS
        """, "BELONGS_TO")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///rel_has_kb.csv' AS row
            MATCH (u:Update {revision_id: row.revision_id})
            MATCH (k:KBArticle {kb_article_id: row.kb_article_id})
            MERGE (u)-[:HAS_KB]->(k)
            } IN TRANSACTIONS OF 5000 ROWS
        """, "HAS_KB")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///rel_fixes.csv' AS row
            MATCH (u:Update {revision_id: row.revision_id})
            MATCH (c:CVE {cve_id: row.cve_id})
            MERGE (u)-[:FIXES]->(c)
            } IN TRANSACTIONS OF 5000 ROWS
        """, "FIXES")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///rel_has_eula.csv' AS row
            MATCH (u:Update {revision_id: row.revision_id})
            MATCH (e:Eula {digest: row.digest})
            MERGE (u)-[:HAS_EULA {requires_reacceptance: (row.requires_reacceptance = 'true')}]->(e)
            } IN TRANSACTIONS OF 1000 ROWS
        """, "HAS_EULA")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///rel_has_language.csv' AS row
            MATCH (u:Update {revision_id: row.revision_id})
            MATCH (l:Language {language_code: row.language_code})
            MERGE (u)-[:HAS_LANGUAGE]->(l)
            } IN TRANSACTIONS OF 5000 ROWS
        """, "HAS_LANGUAGE (Update)")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///rel_eula_language.csv' AS row
            MATCH (e:Eula {digest: row.digest})
            MATCH (l:Language {language_code: row.language_code})
            MERGE (e)-[:HAS_LANGUAGE]->(l)
            } IN TRANSACTIONS OF 1000 ROWS
        """, "HAS_LANGUAGE (Eula)")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///rel_depends_on.csv' AS row
            MATCH (src:Update {revision_id: row.source_revision_id})
            MATCH (tgt:Update {update_id: row.target_update_id})
            MERGE (src)-[:DEPENDS_ON {is_or: (row.is_or = 'True')}]->(tgt)
            } IN TRANSACTIONS OF 500 ROWS
        """, "DEPENDS_ON")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///rel_bundled_by.csv' AS row
            MATCH (u:Update {revision_id: row.revision_id})
            MATCH (bundle:Update {revision_id: row.bundle_update_id})
            MERGE (u)-[:BUNDLED_BY]->(bundle)
            } IN TRANSACTIONS OF 500 ROWS
        """, "BUNDLED_BY")

        run(session, """
            CALL () {
            LOAD CSV WITH HEADERS FROM 'file:///rel_superseded_by.csv' AS row
            MATCH (u:Update {revision_id: row.revision_id})
            MATCH (sup:Update {revision_id: row.superseding_update_id})
            MERGE (u)-[:SUPERSEDED_BY]->(sup)
            } IN TRANSACTIONS OF 500 ROWS
        """, "SUPERSEDED_BY")

        print("\n=== Phase 4 — Vérification ===")

        result = session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC")
        print("\nNoeuds :")
        for r in result:
            print(f"  {r['label']}: {r['count']}")

        result = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count ORDER BY count DESC")
        print("\nRelations :")
        for r in result:
            print(f"  {r['type']}: {r['count']}")

    driver.close()
    print("\nImport terminé.")