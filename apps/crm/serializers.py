from rest_framework import serializers

from .models import (
    ClientContact, ClientContract, ClientMeetingNote,
    ClientSLA, Placement, RecruitmentClient,
)


class RecruitmentClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecruitmentClient
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'company_id', 'tenant_id']


class ClientContactSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)

    class Meta:
        model = ClientContact
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'company_id', 'tenant_id']


class ClientSLASerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientSLA
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'company_id', 'tenant_id']


class ClientContractSerializer(serializers.ModelSerializer):
    slas = ClientSLASerializer(many=True, read_only=True)
    client_name = serializers.CharField(source='client.name', read_only=True)

    class Meta:
        model = ClientContract
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'company_id', 'tenant_id']


class ClientMeetingNoteSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)

    class Meta:
        model = ClientMeetingNote
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'company_id', 'tenant_id']


class PlacementSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source='candidate.full_name', read_only=True)
    client_name = serializers.CharField(source='client.name', read_only=True)

    class Meta:
        model = Placement
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'company_id', 'tenant_id']
