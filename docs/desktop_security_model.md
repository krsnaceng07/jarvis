# Desktop Security & Wrong-Recipient Protection Model

## 1. Risk Classification
- **Read-Only / Inspection**: Capturing screenshots, reading titles, reading text $ightarrow$ Pre-authorized.
- **Local Mutation**: Typing text in a scratchpad, opening a file $ightarrow$ Allowed with active task grounding.
- **External Side-Effects**: Sending messages/emails, deleting files, changing security settings $ightarrow$ Confirmation required.

## 2. Wrong-Recipient Protection for Messaging
1. **Contact Disambiguation**: If multiple contacts match (e.g. 3 Johns), JARVIS stops and asks the user to clarify.
2. **Pre-Send Recipient Assertion**: The active chat header text MUST strictly match the intended recipient.
3. **Exact Message Match**: Typed input MUST character-match the user's requested text before the Send button is triggered.
