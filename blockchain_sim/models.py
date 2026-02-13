from django.db import models
import uuid


class SimulationConfig(models.Model):
    num_nodes = models.IntegerField(default=5)
    difficulty = models.IntegerField(default=2)
    min_delay = models.FloatField(default=0.1, help_text="Min network delay in seconds")
    max_delay = models.FloatField(default=0.5, help_text="Max network delay in seconds")
    is_running = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.pk and SimulationConfig.objects.exists():
            return SimulationConfig.objects.first().save(*args, **kwargs)
        return super().save(*args, **kwargs)


class Node(models.Model):
    id = models.CharField(max_length=64, primary_key=True, editable=False)
    name = models.CharField(max_length=100)
    is_malicious = models.BooleanField(default=False)
    balance = models.FloatField(default=0.0)
    status = models.CharField(max_length=20, default="active")

    reputation = models.FloatField(default=100.0)
    packets_sent = models.IntegerField(default=0)
    packets_received = models.IntegerField(default=0)
    packets_dropped = models.IntegerField(default=0)
    trade_success_count = models.IntegerField(default=0)
    trade_failure_count = models.IntegerField(default=0)

    def __str__(self):
        return self.name


class MetricLog(models.Model):
    timestamp = models.FloatField()
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="metrics")
    metric_type = models.CharField(max_length=50)
    value = models.FloatField()

    class Meta:
        ordering = ["-timestamp"]


class Block(models.Model):
    index = models.IntegerField()
    timestamp = models.FloatField()
    previous_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)
    validator = models.ForeignKey(Node, on_delete=models.CASCADE, null=True)
    nonce = models.IntegerField(default=0)

    class Meta:
        ordering = ["-index"]


class Transaction(models.Model):
    sender = models.ForeignKey(Node, related_name="sent_txs", on_delete=models.CASCADE)
    receiver = models.ForeignKey(
        Node, related_name="received_txs", on_delete=models.CASCADE
    )
    amount = models.FloatField()
    timestamp = models.FloatField()
    block = models.ForeignKey(
        Block,
        related_name="transactions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )


class NetworkEvent(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    node = models.ForeignKey(Node, on_delete=models.CASCADE, null=True, blank=True)
    event_type = models.CharField(max_length=50)
    message = models.TextField()

    class Meta:
        ordering = ["-timestamp"]
