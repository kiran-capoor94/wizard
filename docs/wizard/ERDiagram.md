# ER Diagram

````mermaid
erDiagram
    User {
        int id PK
        string email
        DateTime createdAt
    }

    Repo {
        int id PK
        string name
        string url
        string platform
        DateTime createdAt
        DateTime updatedAt
    }

    Meeting {
        int id PK
        string title
        string outline
        string[] keyPoints
        string krispUrl
        string notionUrl
        int repoId FK
        DateTime createdAt
        DateTime updatedAt
    }

    ActionItem {
        int id PK
        string action
        DateTime dueDate
        int meetingId FK
        int taskId FK
        DateTime createdAt
    }

    Task {
        int id PK
        string title
        string description
        TaskStatus status
        TaskPriority priority
        DateTime dueDate
        TaskType taskType
        string externalTaskId
        string branch
        int repoId FK
        int meetingId FK
        int createdById FK
        DateTime createdAt
        DateTime updatedAt
    }

    Session {
        int id PK
        SessionStatus status
        Json workflowState
        int meetingId FK
        int createdById FK
        DateTime startedAt
        DateTime endedAt
        DateTime createdAt
        DateTime updatedAt
    }

    SessionTask {
        int sessionId PK
        int taskId PK
    }

    Note {
        int id PK
        string title
        string note
        NoteType type
        int meetingId FK
        int taskId FK
        int sessionId FK
        int repoId FK
        int createdById FK
        DateTime createdAt
    }

    WorkflowRun {
        int id PK
        string workflowId
        int sessionId FK
        int taskId FK
        WorkflowStatus status
        Json input
        Json output
        DateTime startedAt
        DateTime completedAt
        DateTime createdAt
        DateTime updatedAt
    }

    CalibrationExample {
        string id PK
        int taskId FK
        int meetingId FK
        boolean label
        float similarity
        DateTime createdAt
    }

    SemanticConfig {
        string id PK
        string key
        float value
        DateTime updatedAt
    }

    IntegrationConfig {
        string id PK
        string source
        string token
        Json metadata
        DateTime createdAt
        DateTime updatedAt
    }

    TaskEmbedding {
        string id PK
        int taskId FK
        vector embedding
        DateTime updatedAt
    }

    MeetingEmbedding {
        string id PK
        int meetingId FK
        vector embedding
        DateTime updatedAt
    }

    NoteEmbedding {
        string id PK
        int noteId FK
        vector embedding
        DateTime updatedAt
    }

    CodeChunkEmbedding {
        string id PK
        int repoId FK
        string filePath
        int startLine
        int endLine
        string content
        string contentHash
        vector embedding
        DateTime updatedAt
    }

    User ||--o{ Task : "creates"
    User ||--o{ Session : "owns"
    User ||--o{ Note : "writes"

    Repo ||--o{ Task : "referenced by"
    Repo ||--o{ Meeting : "referenced by"
    Repo ||--o{ Note : "referenced by"
    Repo ||--o{ CodeChunkEmbedding : "chunked into"

    Meeting ||--o{ Task : "originates"
    Meeting ||--o{ ActionItem : "produces"
    Meeting ||--o{ Session : "triggers"
    Meeting ||--o{ Note : "generates"
    Meeting ||--o| MeetingEmbedding : "embedded as"
    Meeting ||--o{ CalibrationExample : "used in"

    ActionItem }o--o| Task : "graduates into"

    Task ||--o| TaskEmbedding : "embedded as"
    Task ||--o{ SessionTask : "worked on in"
    Task ||--o{ Note : "documented in"
    Task ||--o{ WorkflowRun : "driven by"
    Task ||--o{ CalibrationExample : "used in"

    Session ||--o{ SessionTask : "contains"
    Session ||--o{ WorkflowRun : "drives"
    Session ||--o{ Note : "produces"

    Note ||--o| NoteEmbedding : "embedded as"```

_End_
````
