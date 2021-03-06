# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

from . import dborgproto_pb2 as dborgproto__pb2


class DashborgServiceStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.Proc = channel.unary_unary(
                '/dashborg.rpc1.DashborgService/Proc',
                request_serializer=dborgproto__pb2.ProcMessage.SerializeToString,
                response_deserializer=dborgproto__pb2.ProcResponse.FromString,
                )
        self.SendResponse = channel.unary_unary(
                '/dashborg.rpc1.DashborgService/SendResponse',
                request_serializer=dborgproto__pb2.SendResponseMessage.SerializeToString,
                response_deserializer=dborgproto__pb2.SendResponseResponse.FromString,
                )
        self.RegisterHandler = channel.unary_unary(
                '/dashborg.rpc1.DashborgService/RegisterHandler',
                request_serializer=dborgproto__pb2.RegisterHandlerMessage.SerializeToString,
                response_deserializer=dborgproto__pb2.RegisterHandlerResponse.FromString,
                )
        self.StartStream = channel.unary_unary(
                '/dashborg.rpc1.DashborgService/StartStream',
                request_serializer=dborgproto__pb2.StartStreamMessage.SerializeToString,
                response_deserializer=dborgproto__pb2.StartStreamResponse.FromString,
                )
        self.ReflectZone = channel.unary_unary(
                '/dashborg.rpc1.DashborgService/ReflectZone',
                request_serializer=dborgproto__pb2.ReflectZoneMessage.SerializeToString,
                response_deserializer=dborgproto__pb2.ReflectZoneResponse.FromString,
                )
        self.CallDataHandler = channel.unary_unary(
                '/dashborg.rpc1.DashborgService/CallDataHandler',
                request_serializer=dborgproto__pb2.CallDataHandlerMessage.SerializeToString,
                response_deserializer=dborgproto__pb2.CallDataHandlerResponse.FromString,
                )
        self.BackendPush = channel.unary_unary(
                '/dashborg.rpc1.DashborgService/BackendPush',
                request_serializer=dborgproto__pb2.BackendPushMessage.SerializeToString,
                response_deserializer=dborgproto__pb2.BackendPushResponse.FromString,
                )
        self.RequestStream = channel.unary_stream(
                '/dashborg.rpc1.DashborgService/RequestStream',
                request_serializer=dborgproto__pb2.RequestStreamMessage.SerializeToString,
                response_deserializer=dborgproto__pb2.RequestMessage.FromString,
                )


class DashborgServiceServicer(object):
    """Missing associated documentation comment in .proto file."""

    def Proc(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def SendResponse(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def RegisterHandler(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def StartStream(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def ReflectZone(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CallDataHandler(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def BackendPush(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def RequestStream(self, request, context):
        """this is backwards since the server sends requests, and the client responds to them
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_DashborgServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'Proc': grpc.unary_unary_rpc_method_handler(
                    servicer.Proc,
                    request_deserializer=dborgproto__pb2.ProcMessage.FromString,
                    response_serializer=dborgproto__pb2.ProcResponse.SerializeToString,
            ),
            'SendResponse': grpc.unary_unary_rpc_method_handler(
                    servicer.SendResponse,
                    request_deserializer=dborgproto__pb2.SendResponseMessage.FromString,
                    response_serializer=dborgproto__pb2.SendResponseResponse.SerializeToString,
            ),
            'RegisterHandler': grpc.unary_unary_rpc_method_handler(
                    servicer.RegisterHandler,
                    request_deserializer=dborgproto__pb2.RegisterHandlerMessage.FromString,
                    response_serializer=dborgproto__pb2.RegisterHandlerResponse.SerializeToString,
            ),
            'StartStream': grpc.unary_unary_rpc_method_handler(
                    servicer.StartStream,
                    request_deserializer=dborgproto__pb2.StartStreamMessage.FromString,
                    response_serializer=dborgproto__pb2.StartStreamResponse.SerializeToString,
            ),
            'ReflectZone': grpc.unary_unary_rpc_method_handler(
                    servicer.ReflectZone,
                    request_deserializer=dborgproto__pb2.ReflectZoneMessage.FromString,
                    response_serializer=dborgproto__pb2.ReflectZoneResponse.SerializeToString,
            ),
            'CallDataHandler': grpc.unary_unary_rpc_method_handler(
                    servicer.CallDataHandler,
                    request_deserializer=dborgproto__pb2.CallDataHandlerMessage.FromString,
                    response_serializer=dborgproto__pb2.CallDataHandlerResponse.SerializeToString,
            ),
            'BackendPush': grpc.unary_unary_rpc_method_handler(
                    servicer.BackendPush,
                    request_deserializer=dborgproto__pb2.BackendPushMessage.FromString,
                    response_serializer=dborgproto__pb2.BackendPushResponse.SerializeToString,
            ),
            'RequestStream': grpc.unary_stream_rpc_method_handler(
                    servicer.RequestStream,
                    request_deserializer=dborgproto__pb2.RequestStreamMessage.FromString,
                    response_serializer=dborgproto__pb2.RequestMessage.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'dashborg.rpc1.DashborgService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class DashborgService(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def Proc(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/dashborg.rpc1.DashborgService/Proc',
            dborgproto__pb2.ProcMessage.SerializeToString,
            dborgproto__pb2.ProcResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def SendResponse(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/dashborg.rpc1.DashborgService/SendResponse',
            dborgproto__pb2.SendResponseMessage.SerializeToString,
            dborgproto__pb2.SendResponseResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def RegisterHandler(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/dashborg.rpc1.DashborgService/RegisterHandler',
            dborgproto__pb2.RegisterHandlerMessage.SerializeToString,
            dborgproto__pb2.RegisterHandlerResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def StartStream(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/dashborg.rpc1.DashborgService/StartStream',
            dborgproto__pb2.StartStreamMessage.SerializeToString,
            dborgproto__pb2.StartStreamResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def ReflectZone(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/dashborg.rpc1.DashborgService/ReflectZone',
            dborgproto__pb2.ReflectZoneMessage.SerializeToString,
            dborgproto__pb2.ReflectZoneResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def CallDataHandler(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/dashborg.rpc1.DashborgService/CallDataHandler',
            dborgproto__pb2.CallDataHandlerMessage.SerializeToString,
            dborgproto__pb2.CallDataHandlerResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def BackendPush(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(request, target, '/dashborg.rpc1.DashborgService/BackendPush',
            dborgproto__pb2.BackendPushMessage.SerializeToString,
            dborgproto__pb2.BackendPushResponse.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)

    @staticmethod
    def RequestStream(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_stream(request, target, '/dashborg.rpc1.DashborgService/RequestStream',
            dborgproto__pb2.RequestStreamMessage.SerializeToString,
            dborgproto__pb2.RequestMessage.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)
