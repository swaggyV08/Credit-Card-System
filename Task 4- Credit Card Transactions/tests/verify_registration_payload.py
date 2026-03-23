from app.schemas.auth import CreateRegistrationRequest
import json

def test_registration_schema():
    schema = CreateRegistrationRequest.model_json_schema()
    name_props = schema["$defs"]["NameSchema"]["properties"] if "$defs" in schema else schema["properties"]["name"]["properties"]
    
    # If using $defs (standard for Pydantic V2)
    if "$defs" in schema:
        name_props = schema["$defs"]["NameSchema"]["properties"]
    
    print(f"Name properties: {list(name_props.keys())}")
    assert "suffix" not in name_props, "Suffix should not be in NameSchema"
    print("Schema verification passed!")

if __name__ == "__main__":
    try:
        test_registration_schema()
    except Exception as e:
        print(f"Verification failed: {e}")
        # Print the whole schema for debugging if it fails
        # print(json.dumps(CreateRegistrationRequest.model_json_schema(), indent=2))
