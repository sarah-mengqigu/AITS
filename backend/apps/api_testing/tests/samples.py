"""Static specification samples used by parser tests."""

OPENAPI3_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Pet API", "version": "1.0.0", "description": "示例接口"},
    "servers": [{"url": "https://api.example.com/v1"}],
    "paths": {
        "/pets": {
            "get": {
                "summary": "宠物列表",
                "operationId": "listPets",
                "tags": ["pets"],
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "example": 10},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Pet"},
                                }
                            }
                        },
                    }
                },
            },
            "post": {
                "summary": "创建宠物",
                "tags": ["pets"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Pet"}
                        }
                    },
                },
                "responses": {"201": {"description": "created"}},
            },
        },
        "/pets/{petId}": {
            "get": {
                "summary": "宠物详情",
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "example": "p1"},
                    }
                ],
                "responses": {"200": {"description": "ok"}},
            }
        },
    },
    "components": {
        "schemas": {
            "Pet": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            }
        }
    },
}

SWAGGER2_SPEC = {
    "swagger": "2.0",
    "info": {"title": "Legacy API", "version": "2.1"},
    "basePath": "/api/v2",
    "paths": {
        "/login": {
            "post": {
                "summary": "登录",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {"$ref": "#/definitions/Login"},
                    },
                    {
                        "name": "X-Token",
                        "in": "header",
                        "type": "string",
                        "example": "abc",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "ok",
                        "schema": {
                            "type": "object",
                            "properties": {"token": {"type": "string"}},
                        },
                    }
                },
            }
        }
    },
    "definitions": {
        "Login": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
        }
    },
}

POSTMAN_COLLECTION = {
    "info": {
        "name": "Demo Collection",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        "version": "2.1.0",
    },
    "variable": [
        {"key": "baseUrl", "value": "https://postman.example.com"},
        {"key": "user", "value": "alice"},
        {"key": "token", "value": "tok-123"},
    ],
    "item": [
        {
            "name": "Auth",
            "item": [
                {
                    "name": "Login",
                    "event": [
                        {
                            "listen": "test",
                            "script": {
                                "exec": [
                                    'pm.test("status ok", function () {',
                                    "    pm.response.to.have.status(200);",
                                    "});",
                                    'pm.test("has token", function () {',
                                    "    const jsonData = pm.response.json();",
                                    '    pm.expect(jsonData.data.token).to.eql("abc123");',
                                    "    pm.expect(jsonData.data.user.id).to.eql(7);",
                                    "});",
                                ]
                            },
                        }
                    ],
                    "request": {
                        "method": "POST",
                        "header": [
                            {"key": "Content-Type", "value": "application/json"}
                        ],
                        "auth": {
                            "type": "bearer",
                            "bearer": [{"key": "token", "value": "{{token}}"}],
                        },
                        "body": {
                            "mode": "raw",
                            "raw": '{"username":"{{user}}","password":"secret"}',
                            "options": {"raw": {"language": "json"}},
                        },
                        "url": {
                            "raw": "{{baseUrl}}/api/login?remember=true",
                            "host": ["{{baseUrl}}"],
                            "path": ["api", "login"],
                            "query": [{"key": "remember", "value": "true"}],
                            "variable": [{"key": "userId", "value": "7"}],
                        },
                    },
                }
            ],
        },
        {
            "name": "Health",
            "request": {
                "method": "GET",
                "url": "https://postman.example.com/health",
            },
        },
    ],
}
