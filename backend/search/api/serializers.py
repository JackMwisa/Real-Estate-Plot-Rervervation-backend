from rest_framework import serializers
from ..models import SavedSearch, SearchEvent


class SavedSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = [
            'id', 'name', 'query_json', 'alerts_enabled', 
            'last_run_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'last_run_at', 'created_at', 'updated_at']


class SearchEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchEvent
        fields = [
            'id', 'query_json', 'result_count', 'took_ms', 
            'source', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']