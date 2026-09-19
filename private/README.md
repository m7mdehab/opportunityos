# Private Local Data

Place founder-specific material here, including CV and résumé text, the Truth Graph, Capability Pack, personal contact details, application history, tracker data, interview notes, salary data, and personal company shortlists.

Everything in this directory is ignored except this file. Never commit secrets here or anywhere else; use the designated secret store.


Founder decision 2026-09-19: the canonical career Truth Pack itself is classified by the Founder as non-sensitive product truth and may be stored outside `private/` for OpportunityOS runtime use. CV PDF bodies still contain personal contact details and are stored in the private Supabase `founder-cv-portfolio` bucket; only their filenames, role mappings and SHA-256 hashes belong in the public repository.
