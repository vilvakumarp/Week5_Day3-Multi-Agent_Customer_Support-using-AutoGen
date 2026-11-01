from database.db_manager import (
    init_db,
    create_organisation,
    create_conversation,
    save_message,
    get_conversation_messages,
    list_conversations
)

# Initialise database
init_db()

# Create organisation
org_id = create_organisation(
    name="Canara Bank",
    domain="Banking",
    official_website="https://canarabank.com"
)

# Create conversation
conversation_id = create_conversation(
    title="Savings Account Enquiry",
    organisation_id=org_id
)

# Save customer message
save_message(
    conversation_id,
    role="user",
    content="What are the savings account requirements?"
)

# Save agent response
save_message(
    conversation_id,
    role="assistant",
    content="I will check the available documentation.",
    agent_name="Customer Support Agent"
)

# Retrieve conversation
messages = get_conversation_messages(conversation_id)

for message in messages:
    print(message["role"], "-", message["content"])

print("\nConversations:", list_conversations())
