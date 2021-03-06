"""
DRS De-Registration device resource package.
Copyright (c) 2018-2020 Qualcomm Technologies, Inc.
All rights reserved.
Redistribution and use in source and binary forms, with or without modification, are permitted (subject to the limitations in the disclaimer below) provided that the following conditions are met:

    Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
    Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
    Neither the name of Qualcomm Technologies, Inc. nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
    The origin of this software must not be misrepresented; you must not claim that you wrote the original software. If you use this software in a product, an acknowledgment is required by displaying the trademark/log as per the details provided here: https://www.qualcomm.com/documents/dirbs-logo-and-brand-guidelines
    Altered source versions must be plainly marked as such, and must not be misrepresented as being the original software.
    This notice may not be removed or altered from any source distribution.

NO EXPRESS OR IMPLIED LICENSES TO ANY PARTY'S PATENT RIGHTS ARE GRANTED BY THIS LICENSE. THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
import json

from flask import Response, request
from flask_restful import Resource
from marshmallow import ValidationError
from flask_babel import lazy_gettext as _

from app import app, db
from app.api.v1.helpers.error_handlers import DEREG_NOT_FOUND_MSG
from app.api.v1.helpers.response import MIME_TYPES, CODES
from app.api.v1.helpers.utilities import Utilities
from app.api.v1.models.deregdetails import DeRegDetails
from app.api.v1.models.deregdevice import DeRegDevice
from app.api.v1.models.status import Status
from app.api.v1.schema.deregdevice import DeRegRequestSchema, DeRegDeviceSchema, DeRegRequestUpdateSchema


class DeRegDeviceRoutes(Resource):
    """Class for handling De Registration Device routes."""

    @staticmethod
    def get(dereg_id):
        """GET method handler, returns device of a request."""
        if not dereg_id.isdigit() or not DeRegDetails.exists(dereg_id):
            return Response(app.json_encoder.encode(DEREG_NOT_FOUND_MSG), status=CODES.get("UNPROCESSABLE_ENTITY"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))
        try:
            schema = DeRegDeviceSchema()
            dereg_devices = DeRegDevice.get_devices_by_dereg_id(dereg_id)
            response = schema.dump(dereg_devices, many=True).data
            return Response(json.dumps(response), status=CODES.get("OK"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))
        except Exception as e:  # pragma: no cover
            app.logger.exception(e)
            error = {
                'message': [_('Failed to retrieve response, please try later')]
            }
            return Response(app.json_encoder.encode(error), status=CODES.get('INTERNAL_SERVER_ERROR'),
                            mimetype=MIME_TYPES.get('APPLICATION_JSON'))
        finally:
            db.session.close()

    @staticmethod
    def post():
        """POST method handler, creates new devices for request."""
        dereg_id = request.form.to_dict().get('dereg_id', None)
        if not dereg_id or not dereg_id.isdigit() or not DeRegDetails.exists(dereg_id):
            return Response(app.json_encoder.encode(DEREG_NOT_FOUND_MSG), status=CODES.get("UNPROCESSABLE_ENTITY"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))
        try:
            schema_request = DeRegRequestSchema()
            device_schema = DeRegDeviceSchema()
            dereg = DeRegDetails.get_by_id(dereg_id)
            args = request.form.to_dict()
            args = DeRegDevice.curate_args(args, dereg)
            validation_errors = schema_request.validate(args)
            if validation_errors:
                return Response(app.json_encoder.encode(validation_errors),
                                status=CODES.get("UNPROCESSABLE_ENTITY"),
                                mimetype=MIME_TYPES.get("APPLICATION_JSON"))
            imei_tac_map = Utilities.extract_imeis_tac_map(args, dereg)
            imeis_list = Utilities.extract_imeis(imei_tac_map)
            not_registered_imeis = Utilities.get_not_registered_imeis(imeis_list)
            if not_registered_imeis:
                error = {
                    'not_registered_imeis': not_registered_imeis
                }
                return Response(json.dumps(error),
                                status=CODES.get("UNPROCESSABLE_ENTITY"),
                                mimetype=MIME_TYPES.get("APPLICATION_JSON"))
            else:
                old_devices = list(map(lambda x: x.id, dereg.devices))
                created = DeRegDevice.bulk_create(args, dereg)
                device_id_tac_map = Utilities.get_id_tac_map(created)
                devices = device_schema.dump(created, many=True)
                dereg_status = 'Pending Review' if app.config['AUTOMATE_IMEI_CHECK'] else 'Awaiting Documents'
                dereg.update_status(dereg_status) # TODO: Change status if automate check is enables
                db.session.commit()
                DeRegDevice.bulk_insert_imeis(device_id_tac_map, imei_tac_map, old_devices, imeis_list, dereg)
                response = {'devices': devices.data, 'dreg_id': dereg.id}
                return Response(json.dumps(response), status=CODES.get("OK"),
                                mimetype=MIME_TYPES.get("APPLICATION_JSON"))
        except Exception as e:  # pragma: no cover
            app.logger.exception(e)
            error = {
                'message': [_('Failed to retrieve response, please try later')]
            }
            return Response(app.json_encoder.encode(error), status=CODES.get('INTERNAL_SERVER_ERROR'),
                            mimetype=MIME_TYPES.get('APPLICATION_JSON'))
        finally:
            db.session.close()

    @staticmethod
    def put():
        """PUT method handler, updates devices of the request."""
        dereg_id = request.form.to_dict().get('dereg_id', None)
        if not dereg_id or not dereg_id.isdigit() or not DeRegDetails.exists(dereg_id):
            return Response(app.json_encoder.encode(DEREG_NOT_FOUND_MSG), status=CODES.get("UNPROCESSABLE_ENTITY"),
                            mimetype=MIME_TYPES.get("APPLICATION_JSON"))
        try:
            schema_request = DeRegRequestUpdateSchema()
            device_schema = DeRegDeviceSchema()
            dereg = DeRegDetails.get_by_id(dereg_id)
            args = request.form.to_dict()
            args = DeRegDevice.curate_args(args, dereg)
            validation_errors = schema_request.validate(args)
            if validation_errors:
                return Response(app.json_encoder.encode(validation_errors),
                                status=CODES.get("UNPROCESSABLE_ENTITY"),
                                mimetype=MIME_TYPES.get("APPLICATION_JSON"))
            imei_tac_map = Utilities.extract_imeis_tac_map(args, dereg)
            imeis_list = Utilities.extract_imeis(imei_tac_map)
            not_registered_imeis = Utilities.get_not_registered_imeis(imeis_list)
            if not_registered_imeis:
                error = {
                    'not_registered_imeis': not_registered_imeis
                }
                return Response(json.dumps(error),
                                status=CODES.get("UNPROCESSABLE_ENTITY"),
                                mimetype=MIME_TYPES.get("APPLICATION_JSON"))
            else:
                # day_passed = (datetime.now() - dereg.updated_at) > timedelta(1)
                processing_failed = dereg.processing_status in [Status.get_status_id('Failed'),
                                                                Status.get_status_id('New Request'),
                                                                Status.get_status_id('Pending Review')]
                report_failed = dereg.report_status == Status.get_status_id('Failed')
                # report_timeout = dereg.report_status == Status.get_status_id('Processing') and day_passed
                processing_required = processing_failed or report_failed
                if processing_required:
                    old_devices = list(map(lambda x: x.id, dereg.devices))
                    created = DeRegDevice.bulk_create(args, dereg)
                    device_id_tac_map = Utilities.get_id_tac_map(created)
                    devices = device_schema.dump(created, many=True)
                    db.session.commit()
                    DeRegDevice.bulk_insert_imeis(device_id_tac_map, imei_tac_map, old_devices, imeis_list, dereg)
                    response = {'devices': devices.data, 'dreg_id': dereg.id}
                else:
                    response = {'devices': [], 'dreg_id': dereg.id}
                return Response(json.dumps(response), status=CODES.get("OK"),
                                mimetype=MIME_TYPES.get("APPLICATION_JSON"))
        except Exception as e:  # pragma: no cover
            app.logger.exception(e)
            error = {
                'message': [_('Failed to retrieve response, please try later')]
            }
            return Response(app.json_encoder.encode(error), status=CODES.get('INTERNAL_SERVER_ERROR'),
                            mimetype=MIME_TYPES.get('APPLICATION_JSON'))
        finally:
            db.session.close()
