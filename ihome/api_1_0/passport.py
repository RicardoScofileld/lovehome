# coding=utf-8
# 导入蓝图对象api
from . import api
# 导入flask内置的对象
from flask import request,jsonify,current_app,session,g
# 导入自定义的状态码
from ihome.utils.response_code import RET
# 导入模型类
from ihome.models import User
# 导入登陆验证装饰器
from ihome.utils.commons import login_required
# 导入sqlalchemy实例
from ihome import db,constants
# 导入七牛云接口
from ihome.utils.image_storage import storage

# 导入正则模块
import re


@api.route('/sessions',methods=['POST'])
def login():
    """
    用户登陆
    1/获取参数,request.get_json()获取post请求的json参数
    2/校验参数存在
    3/获取详细的参数信息,mobile,password
    4/校验参数的完整性
    5/校验手机号格式
    6/判断手机号已注册,以及密码校验
    user = User.query.filter_by(mobile=mobile).first()
    7/校验查询结果并判断密码
    8/缓存用户信息
    session['user_id'] = user.id
    session['name'] = user.name(登陆时缓存的用户信息,不能是手机号)
    session['mobile'] = mobile
    9/返回结果

    :return:
    """
    # 获取参数,使用get_json()方法
    user_data = request.get_json()
    # 判断参数存在
    if not user_data:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 获取详细的参数的信息
    mobile = user_data.get('mobile')
    password = user_data.get('password')
    # 校验参数的完整性
    if not all([mobile,password]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数缺失')
    # 校验手机号格式
    if not re.match(r'1[3456789]\d{9}$',mobile):
        return jsonify(errno=RET.PARAMERR,errmsg='手机号格式错误')
    # 查询mysql数据库,确认用户存在
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询用户信息失败')
    # 校验查询结果,以及对密码进行判断
    if user is None or not user.check_password(password):
        return jsonify(errno=RET.DATAERR,errmsg='用户名或密码错误')
    # 缓存用户信息到redis中
    session['user_id'] = user.id
    session['name'] = user.name
    session['mobile'] = mobile
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={'user_id':user.id})


@api.route('/user',methods=['GET'])
@login_required
def get_user_profile():
    """
    获取用户信息
    1/通过登陆装饰验证器,获取用户身份,user_id = g.user_id
    2/根据user_id查询mysql数据库
    user = User.query.filter_by(id=user_id).first()
    3/判断查询结果
    4/返回结果
    data=user.to_dict()
    :return:
    """
    # 获取用户身份
    user_id = g.user_id
    # 查询mysql数据库
    try:
        # User.query.get(user_id)
        user = User.query.filter_by(id=user_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询用户信息失败')
    # 校验查询结果
    if not user:
        return jsonify(errno=RET.NODATA,errmsg='无效操作')
    # 返回结果,to_dict()方法为模型类中的实例方法;
    return jsonify(errno=RET.OK,errmsg='OK',data=user.to_dict())


@api.route('/user/name',methods=['PUT'])
@login_required
def change_user_profile():
    """
    修改用户信息
    1/获取用户身份,获取参数request.get_json()
    2/校验参数存在
    3/获取详细的参数信息,name值
    4/校验name参数存在
    5/查询数据库,保存用户更新后的用户名信息
    User.query.filter_by(id=user_id).update({'name':name})
    db.session.commit()
    db.session.rollback()
    6/更新redis缓存中用户名信息
    7/返回结果

    :return:
    """
    # 获取user_id
    user_id = g.user_id
    # 获取put请求的参数信息
    user_name = request.get_json()
    # 校验参数存在
    if not user_name:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 获取详细的参数信息
    name = user_name.get('name')
    # 校验name参数存在
    if not name:
        return jsonify(errno=RET.PARAMERR,errmsg='参数缺失')
    # 更新用户信息,根据user_id查询数据库
    try:
        User.query.filter_by(id=user_id).update({'name':name})
        # 提交数据到数据库
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        # 如果发生异常,需要进行回滚
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='更新用户信息失败')
    # redis缓存数据更新
    session['name'] = name
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={'name':name})


@api.route('/user/avatar',methods=['POST'])
@login_required
def set_user_avatar():
    """
    设置用户头像
    1/获取用户身份
    2/获取图片文件的参数信息,request.files.get('avatar')
    3/校验参数存在
    4/读取图片数据,传入七牛云接口
    5/调用七牛云,实现文件上传,返回的图片名称
    6/保存图片名称到mysql数据库
    User.query.filter_by(id=user_id).update({'avatar_url':image_name})
    7/提交数据,如果发生异常需要进行回滚
    8/拼接图片的绝对路径,七牛云的外链域名+image_name
    9/返回结果

    :return:
    """
    # 获取user_id
    user_id = g.user_id
    # 获取图片文件参数
    avatar = request.files.get("avatar")
    # 判断数据存在
    if not avatar:
        return jsonify(errno=RET.PARAMERR,errmsg='未上传图片')
    # 读取图片数据
    avatar_data = avatar.read()
    # 调用七牛云接口,实现图片文件的上传
    try:
        image_name = storage(avatar_data)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR,errmsg='七牛云上传图片失败')
    # 保存图片名称到mysql数据库中
    try:
        User.query.filter_by(id=user_id).update({'avatar_url':image_name})
        # 提交数据
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存用户头像失败')
    # 返回前端用户头像的绝对路径
    image_url = constants.QINIU_DOMIN_PREFIX + image_name
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK',data={'avatar_url':image_url})


@api.route('/user/auth',methods=['POST'])
@login_required
def set_user_auth():
    """
    设置实名信息
    1/获取用户身份
    2/获取post请求的参数
    3/校验参数存在
    4/进一步获取详细的参数信息,real_name,id_card
    5/校验参数的完整性
    6/操作mysql数据库,保存用户的实名信息,
    User.query.filter_by(id=user_id,real_name=None,id_card=None).update({'real_name':real_name,'id_card':id_card})
    7/提交数据,发生异常需要进行回滚
    8/返回结果

    :return:
    """
    # 获取用户身份
    user_id = g.user_id
    # 获取post请求的参数
    user_data = request.get_json()
    # 校验数据存在
    if not user_data:
        return jsonify(errno=RET.PARAMERR,errmsg='参数错误')
    # 获取详细的参数信息
    real_name = user_data.get('real_name')
    id_card = user_data.get('id_card')
    # 校验参数的完整性
    if not all([real_name,id_card]):
        return jsonify(errno=RET.PARAMERR,errmsg='参数缺失')
    # 操作mysql数据库,保存用户实名信息
    try:
        User.query.filter_by(id=user_id,real_name=None,id_card=None).update({'real_name':real_name,'id_card':id_card})
        # 提交数据
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR,errmsg='保存用户实名信息失败')
    # 返回结果
    return jsonify(errno=RET.OK,errmsg='OK')

@api.route('/user/auth',methods=['GET'])
@login_required
def get_user_auth():
    """
    获取用户实名信息
    1/获取用户身份信息,user_id
    2/查询mysql数据库,获取用户的实名信息
    3/校验查询结果
    4/返回结果user.auth_to_dict()
    :return:
    """
    # 获取用户身份
    user_id = g.user_id
    # 查询mysql数据库
    try:
        # User.query.get(user_id)
        user = User.query.filter_by(id=user_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR,errmsg='查询用户实名信息失败')
    # 校验查询结果
    if not user:
        return jsonify(errno=RET.NODATA,errmsg='无效操作')
    # 返回实名信息
    return jsonify(errno=RET.OK,errmsg='OK',data=user.auth_to_dict())


@api.route('/session',methods=['DELETE'])
@login_required
def logout():
    """
    退出登陆
    session.clear()
    退出的本质是把服务器缓存的用户信息清除
    :return:
    """
    csrf_token = session.get('csrf_token')
    session.clear()
    session['csrf_token'] = csrf_token
    return jsonify(errno=RET.OK,errmsg='OK')


@api.route('/session',methods=['GET'])
def check_login():
    """
    检查用户登陆状态
    1/使用请求上下文对象,session获取用户缓存用户信息
    session.get('name')
    2/判断获取结果是否有数据,如果用户登陆,返回name
    3/否则返回错误信息
    :return:
    """
    # 从redis数据库中获取用户的缓存信息
    name = session.get('name')
    # 判断获取结果
    if name is not None:
        return jsonify(errno=RET.OK,errmsg='true',data={'name':name})
    else:
        return jsonify(errno=RET.SESSIONERR,errmsg='false')


