# Plan

This plan describes a number of releases where we focus on
individual parts of the full implementation. Some features
ahve already been implemented in the initial version, but
they may be incomplete and we want to methodologically go
through them.

## 0.2 (DONE)

- CreateDocument: (CreateDocumentRequest) -> (Document)
- DeleteDocument: (DeleteDocumentRequest) -> Empty
- GetDocument: (GetDocumentRequest) -> Document
- UpdateDocument: (UpdateDocumentRequest) -> Document
- Write: (WriteRequest) -> WriteResponse
- **Atomic File Operations**: Use a temporary file and `os.replace` for atomic writes.
- **File Locking**: Implement cross-platform file locking for concurrent safety.
- **ISO Timestamps**: Store `SERVER_TIMESTAMP` as ISO datetime strings with explicit type tagging.

## 0.3 (TODO)

- BatchWrite: (BatchWriteRequest) -> BatchWriteResponse
- BatchGetDocuments: BatchGetDocumentsRequest -> (BatchGetDocumentsResponse)

## 0.4 (TODO)

- RunQuery: (RunQuery) -> RunQueryResponse

## 0.5 (TODO)

- ListCollectionIds: (ListCollectionIdsRequest) -> ListCollectionIdsResponse
- ListDocuments: (ListDocumentsRequest) -> ListDocumentsResponse

## 0.6 (TODO)

- RunAggregationQuery: (RunAggregationQueryRequest) -> RunAggregationQueryResponse
- ExecutePipeline: (ExecutePipelineRequest) -> ExecutePipelineResponse
- PartitionQuery: (PartitionQueryRequest) -> PartitionQueryResponse

## 0.7 (DONE)

- BeginTransaction: (BeginTransactionRequest) -> BeginTransactionResponse
- Commit: (CommitRequest) -> CommitResponse
- Rollback: (RollbackRequest) -> Empty


## 0.8 (TODO)

- Listen: (ListenRequest) -> ListenResponse

---

## 0.9 (TODO)

Deep dive on:

- CreateDocumentRequest
- Document
- DeleteDocumentRequest
- GetDocumentRequest
- UpdateDocumentRequest
- WriteRequest
- WriteResponse

## 0.10 (TODO)

Deep dive on:

- BatchWriteRequest
- BatchWriteResponse
- BatchGetDocumentsRequest
- BatchGetDocumentsResponse

## 0.11 (TODO)

Deep dive on:

- RunQuery
- RunQueryResponse

## 0.12 (TODO)

Deep dive on:

- ListCollectionIdsRequest
- ListCollectionIdsResponse
- ListDocumentsRequest
- ListDocumentsResponse

## 0.13 (TODO)

- RunAggregationQueryRequest
- RunAggregationQueryResponse
- ExecutePipelineRequest
- ExecutePipelineResponse
- PartitionQueryRequest
- PartitionQueryResponse

## 0.14 (DONE)

- BeginTransactionRequest
- BeginTransactionResponse
- CommitRequest
- CommitResponse
- RollbackRequest


## 0.15 (TODO)

- ListenRequest
- ListenResponse

## ???
- FieldTransform
- Precondition
