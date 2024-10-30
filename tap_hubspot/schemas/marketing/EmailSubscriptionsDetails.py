from singer_sdk import typing as th  # JSON Schema typing helpers

schema = th.PropertiesList(
    th.Property("businessUnitId", th.IntegerType),
    th.Property("channel", th.StringType),
    th.Property("subscriberIdString", th.StringType),
    th.Property("subscriptionId", th.IntegerType),
    th.Property("status", th.StringType),
    th.Property("source", th.StringType),
    th.Property("legalBasis", th.StringType),
    th.Property("legalBasisExplanation", th.StringType),
    th.Property("setStatusSuccessReason", th.StringType),
    th.Property("timestamp", th.DateTimeType)
).to_dict()
