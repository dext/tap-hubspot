from singer_sdk import typing as th  # JSON Schema typing helpers

schema = th.PropertiesList(
    th.Property("id", th.IntegerType),
    th.Property("businessUnitId", th.IntegerType),
    th.Property("name", th.StringType),
    th.Property("description", th.StringType),
    th.Property("purpose", th.StringType),
    th.Property("communicationMethod", th.StringType),
    th.Property("isActive", th.BooleanType),
    th.Property("isDefault", th.BooleanType),
    th.Property("isInternal", th.BooleanType),
    th.Property("createdAt", th.DateTimeType),
    th.Property("updatedAt", th.DateTimeType)
).to_dict()
