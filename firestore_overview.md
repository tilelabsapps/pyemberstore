# Firestore overview

## Procedures

- BatchGetDocuments: BatchGetDocumentsRequest -> (BatchGetDocumentsResponse)
- BatchWrite: (BatchWriteRequest) -> BatchWriteResponse
- BeginTransaction: (BeginTransactionRequest) -> BeginTransactionResponse
- Commit: (CommitRequest) -> CommitResponse
- CreateDocument: (CreateDocumentRequest) -> (Document)
- DeleteDocument: (DeleteDocumentRequest) -> Empty
- ExecutePipeline: (ExecutePipelineRequest) -> ExecutePipelineResponse
- GetDocument: (GetDocumentRequest) -> Document
- ListCollectionIds: (ListCollectionIdsRequest) -> ListCollectionIdsResponse
- ListDocuments: (ListDocumentsRequest) -> ListDocumentsResponse
- Listen: (ListenRequest) -> ListenResponse
- PartitionQuery: (PartitionQueryRequest) -> PartitionQueryResponse
- Rollback: (RollbackRequest) -> Empty
- RunAggregationQuery: (RunAggregationQueryRequest) -> RunAggregationQueryResponse
- RunQuery: (RunQuery) -> RunQueryResponse
- UpdateDocument: (UpdateDocumentRequest) -> Document
- Write: (WriteRequest) -> WriteResponse


## Requests

- BatchGetDocumentsRequest (message)
- BatchWriteRequest (message)
- BeginTransactionRequest (message)
- CommitRequest (message)
- CreateDocumentRequest (message)
- DeleteDocumentRequest (message)
- ExecutePipelineRequest (message)
- GetDocumentRequest (message)
- ListCollectionIdsRequest (message)
- ListDocumentsRequest (message)
- ListenRequest (message)
- PartitionQueryRequest (message)
- RollbackRequest (message)
- RunAggregationQueryRequest (message)
- RunQueryRequest (message)
- UpdateDocumentRequest (message)

## Responses

- BatchGetDocumentsResponse (message)
- BatchWriteResponse (message)
- BeginTransactionResponse (message)
- CommitResponse (message)
- ExecutePipelineResponse (message)
- ListCollectionIdsResponse (message)
- ListDocumentsResponse (message)
- ListenResponse (message)
- PartitionQueryResponse (message)
- RunAggregationQueryResponse (message)
- RunQueryResponse (message)

## Support types

- AggregationResult (message)
- ArrayValue (message)
- BitSequence (message)
- BloomFilter (message)
- Cursor (message)
- Document (message)
- DocumentChange (message)
- DocumentDelete (message)
- DocumentMask (message)
- DocumentRemove (message)
- DocumentTransform (message)
- DocumentTransform.FieldTransform (message)
- DocumentTransform.FieldTransform.ServerValue (enum)
- ExecutionStats (message)
- ExistenceFilter (message)
- ExplainMetrics (message)
- ExplainOptions (message)
- ExplainStats (message)
- Function (message)
- MapValue (message)
- Pipeline (message)
- Pipeline.Stage (message)
- PlanSummary (message)
- Precondition (message)
- StructuredAggregationQuery (message)
- StructuredAggregationQuery.Aggregation (message)
- StructuredAggregationQuery.Aggregation.Avg (message)
- StructuredAggregationQuery.Aggregation.Count (message)
- StructuredAggregationQuery.Aggregation.Sum (message)
- StructuredPipeline (message)
- StructuredQuery (message)
- StructuredQuery.CollectionSelector (message)
- StructuredQuery.CompositeFilter (message)
- StructuredQuery.CompositeFilter.Operator (enum)
- StructuredQuery.Direction (enum)
- StructuredQuery.FieldFilter (message)
- StructuredQuery.FieldFilter.Operator (enum)
- StructuredQuery.FieldReference (message)
- StructuredQuery.Filter (message)
- StructuredQuery.FindNearest (message)
- StructuredQuery.FindNearest.DistanceMeasure (enum)
- StructuredQuery.Order (message)
- StructuredQuery.Projection (message)
- StructuredQuery.UnaryFilter (message)
- StructuredQuery.UnaryFilter.Operator (enum)
- Target (message)
- Target.DocumentsTarget (message)
- Target.QueryTarget (message)
- TargetChange (message)
- TargetChange.TargetChangeType (enum)
- TransactionOptions (message)
- TransactionOptions.ReadOnly (message)
- TransactionOptions.ReadWrite (message)
- Value (message)
- Write (message)
- WriteRequest (message)
- WriteResponse (message)
- WriteResult (message)

[docs]: https://firebase.google.com/docs/firestore/reference/rpc/google.firestore.v1#google.firestore.v1.Firestore