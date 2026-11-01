# Karnataka Bank Customer Support Demo

This Streamlit demo adds customer login and customer-owned conversation history to the existing AutoGen/RAG support workflow. Authentication is simulated; it is not connected to banking systems.

Run the demo with:

```powershell
python seed_demo_customers.py
streamlit run app.py
```
Use credentails.txt file contents  to login


The seed script is idempotent. Demo records are stored in SQLite with hashed account/mobile lookup values and PBKDF2-hashed PINs. The existing ChromaDB knowledge base and organisation records are preserved.
