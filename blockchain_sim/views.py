from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Node, Block, NetworkEvent, SimulationConfig, MetricLog, Transaction
from .core.simulation_engine import simulation_engine
from django.db.models import Avg
import time


def index(request):
    config = SimulationConfig.objects.first()
    if not config:
        config = SimulationConfig.objects.create()
    return render(request, "dashboard.html", {"config": config})


def node_detail(request, node_id):
    node = get_object_or_404(Node, id=node_id)
    recent_metrics = MetricLog.objects.filter(node=node).order_by("-timestamp")[:50]
    live_node = next(
        (n for n in simulation_engine.nodes if str(n.node_id) == str(node_id)), None
    )
    network_config = live_node.network_config if live_node else {}

    return render(
        request,
        "node_detail.html",
        {"node": node, "metrics": recent_metrics, "network_config": network_config},
    )


def get_node_details_api(request, node_id):
    node = get_object_or_404(Node, id=node_id)
    params = simulation_engine.network_params or {}
    live_node = next(
        (n for n in simulation_engine.nodes if str(n.node_id) == str(node_id)), None
    )
    network_config = live_node.network_config if live_node else {}
    recent_metrics_qs = MetricLog.objects.filter(node=node).order_by("-timestamp")[:20]
    recent_metrics = list(recent_metrics_qs.values("timestamp", "metric_type", "value"))

    data = {
        "id": node.id,
        "name": node.name,
        "balance": node.balance,
        "reputation": node.reputation,
        "is_malicious": node.is_malicious,
        "packets_sent": node.packets_sent,
        "packets_received": node.packets_received,
        "packets_dropped": node.packets_dropped,
        "trade_success_count": node.trade_success_count,
        "trade_failure_count": node.trade_failure_count,
        "network_config": network_config,
        "metrics": recent_metrics,
    }
    return JsonResponse(data)


@csrf_exempt
def start_simulation(request):
    if request.method == "POST":
        num_nodes = int(request.POST.get("num_nodes", 5))
        delay = float(request.POST.get("delay", 0.1))

        Node.objects.all().delete()
        Block.objects.all().delete()
        NetworkEvent.objects.all().delete()
        MetricLog.objects.all().delete()

        config = SimulationConfig.objects.first()
        if not config:
            config = SimulationConfig.objects.create()
        config.num_nodes = num_nodes
        config.min_delay = delay
        config.max_delay = delay * 2

        network_mode = request.POST.get("network_mode", "fixed")

        config.save()

        simulation_engine.start(
            network_mode=network_mode,
            network_params={"min_delay": delay, "max_delay": delay * 2},
        )
        return JsonResponse({"status": "started"})
    return JsonResponse({"status": "error"}, status=400)


@csrf_exempt
def update_node_delay(request):
    if request.method == "POST":
        node_id = int(request.POST.get("node_id"))
        delay = float(request.POST.get("delay"))
        config = {"delay_range": (delay, delay + 0.05)}

        success = simulation_engine.update_node_network_config(node_id, config)
        if success:
            return JsonResponse(
                {"status": "updated", "node_id": node_id, "config": config}
            )
        return JsonResponse({"status": "node_not_found"}, status=404)
    return JsonResponse({"status": "error"}, status=400)


@csrf_exempt
def stop_simulation(request):
    simulation_engine.stop()
    time.sleep(0.5)

    Node.objects.all().delete()
    Block.objects.all().delete()
    NetworkEvent.objects.all().delete()
    MetricLog.objects.all().delete()

    return JsonResponse({"status": "stopped"})


def get_status(request):
    nodes_qs = Node.objects.values(
        "id",
        "name",
        "status",
        "balance",
        "reputation",
        "packets_sent",
        "packets_received",
        "packets_dropped",
    )
    nodes = []

    live_nodes_map = {str(n.node_id): n for n in simulation_engine.nodes}

    for n_dict in nodes_qs:
        live_node = live_nodes_map.get(str(n_dict["id"]))
        if live_node:
            n_dict["network_config"] = live_node.network_config
        nodes.append(n_dict)

    blocks = list(
        Block.objects.values("index", "hash", "validator__name", "timestamp").order_by(
            "-index"
        )[:10]
    )
    events = list(
        NetworkEvent.objects.values(
            "timestamp", "event_type", "message", "node__name"
        ).order_by("-timestamp")[:50]
    )

    return JsonResponse(
        {
            "nodes": nodes,
            "blocks": blocks,
            "events": events,
            "is_running": simulation_engine.is_running,
            "network_mode": simulation_engine.network_mode,
            "num_nodes": simulation_engine.num_nodes,
            "delay": simulation_engine.network_params.get("min_delay", 0.1),
        }
    )


@csrf_exempt
def get_metrics(request):
    now = time.time()

    if not MetricLog.objects.exists():
        return JsonResponse(
            {"block_rate": [], "latency": [], "block_commits": [], "msg_stats": {}}
        )

    from django.db.models import Min

    min_ts = MetricLog.objects.aggregate(Min("timestamp"))["timestamp__min"]

    bucket_size = 5
    num_buckets = 20
    window_start = now - (bucket_size * num_buckets)

    effective_start = max(window_start, min_ts - (min_ts % bucket_size))
    buckets = {}
    current_bucket_time = effective_start
    while current_bucket_time < now + bucket_size:
        t = int(current_bucket_time)
        t = t - (t % bucket_size)
        buckets[t] = {"commits": 0, "latency_sum": 0.0, "latency_count": 0}
        current_bucket_time += bucket_size

    commits = MetricLog.objects.filter(
        metric_type="block_committed", timestamp__gte=effective_start
    )
    for c in commits:
        t = int(c.timestamp)
        t = t - (t % bucket_size)
        if t in buckets:
            buckets[t]["commits"] += 1

    latencies = MetricLog.objects.filter(
        metric_type="latency", timestamp__gte=effective_start
    )
    for l in latencies:
        t = int(l.timestamp)
        t = t - (t % bucket_size)
        if t in buckets:
            buckets[t]["latency_sum"] += l.value
            buckets[t]["latency_count"] += 1

    metrics_data = {"msg_stats": {}}

    sorted_times = sorted(buckets.keys())

    metrics_data["block_commits"] = [
        {"time": t, "value": buckets[t]["commits"] * (60 / bucket_size)}
        for t in sorted_times
    ]

    metrics_data["latency"] = []
    for t in sorted_times:
        b = buckets[t]
        avg = b["latency_sum"] / b["latency_count"] if b["latency_count"] > 0 else 0
        metrics_data["latency"].append({"time": t, "value": avg})

    nodes = Node.objects.all()
    for n in nodes:
        metrics_data["msg_stats"][n.name] = {
            "sent": n.packets_sent,
            "recv": n.packets_received,
            "dropped": n.packets_dropped,
        }

    return JsonResponse(metrics_data)
