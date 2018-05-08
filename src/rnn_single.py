import numpy as np
import pandas as pd
import tensorflow as tf
import matplotlib.pyplot as plt
import os, pickle

HIDDEN_SIZE = 64                            # LSTM中隐藏节点的个数。
NUM_LAYERS = 2                              # LSTM的层数。
TIMESTEPS = 30                              # 循环神经网络的训练序列长度。
TRAINING_STEPS = 5000                      # 训练轮数。
BATCH_SIZE = 16                             # batch大小。

pvars = ['open', 'close', 'high', 'low']

def generate_data(stock):
    if os.path.exists("data_000001.npy"):
        data = np.load('data_000001.npy')
        label = np.load('label_000001.npy')
    else:
        try:
            import QUANTAXIS as qa
            candles = qa.QA_fetch_stock_day_adv(stock, start='2014-01-01', end='2018-05-02')
            cdata = candles.data.reset_index(level=1, drop=True).loc[:, pvars]
            # mid = []
            pdata = []
            plabel = []
            for x in range(cdata.shape[0]-TIMESTEPS):
                # mid.append(cdata.iloc[x: x+TIMESTEPS, :])
                day = cdata.iloc[x: x+TIMESTEPS, :] / cdata.ix[x+TIMESTEPS-1, 'close'] - 1
                pdata.append(day.values.flatten())
                plabel.append(cdata.ix[x+TIMESTEPS, 'close'] / cdata.ix[x+TIMESTEPS-1, 'close'] - 1)
            data = np.asarray(pdata, dtype=np.float32)
            label = np.asarray(plabel, dtype=np.float32)
            np.save('data_000001', data)
            np.save('label_000001', label)
            print('data saved')
        except Exception as e:
            print(e.message)
    return data, label


data, label = generate_data('000001')

print(len(data))
#print(data[:2])
#print(label[:2])

train_X = data[:950]
train_y = label[:950]
test_X = data[950:]
test_y = label[950:]

n_input = 4
n_classes = 1

weights = {
    'hidden': tf.Variable(tf.random_normal([n_input, HIDDEN_SIZE])),  # Hidden layer weights
    'out': tf.Variable(tf.random_normal([HIDDEN_SIZE, n_classes]))
}
biases = {
    'hidden': tf.Variable(tf.random_normal([HIDDEN_SIZE])),
    'out': tf.Variable(tf.random_normal([n_classes]), name='biases')
}

def lstm_model(X, y, is_training, weights, biases):

    # 规整成矩阵数据
    X = tf.reshape(X, [-1, TIMESTEPS, n_input])

    ## 规整输入的数据
    X = tf.transpose(X, [1, 0, 2])  # permute n_steps and batch_size
    X = tf.reshape(X, [-1, n_input])  # (n_steps*batch_size, n_input)
    ## 输入层到隐含层，第一次是直接运算
    X = tf.matmul(X, weights['hidden']) + biases['hidden']  # tf.matmul(a,b)   将矩阵a乘以矩阵b，生成a * b

    # 之后使用LSTM

    # 使用多层的LSTM结构。
    cell = tf.nn.rnn_cell.MultiRNNCell([
        tf.nn.rnn_cell.BasicLSTMCell(HIDDEN_SIZE, forget_bias=1.0, state_is_tuple=True)
        for _ in range(NUM_LAYERS)])

    # 使用TensorFlow接口将多层的LSTM结构连接成RNN网络并计算其前向传播结果。
    # X = tf.split(X, TIMESTEPS, 0)
    X = tf.reshape(X, [-1, TIMESTEPS, HIDDEN_SIZE])
    outputs, _ = tf.nn.dynamic_rnn(cell, X, dtype=tf.float32)
    output = outputs[:, -1, :]

    # 对LSTM网络的输出再做加一层全链接层并计算损失。注意这里默认的损失为平均
    # 平方差损失函数。
    predictions = tf.matmul(output, weights['out'], name='logits_rnn_out') + biases['out']

    # predictions = tf.contrib.layers.fully_connected(output, 1, activation_fn=None)
    # predictions.set_shape([None, 1])
    # y.set_shape([None, 1])
    # print(tf.shape(predictions))
    # print(y.shape)

    # 只在训练时计算损失函数和优化步骤。测试时直接返回预测结果。
    if not is_training:
        return predictions, None, None

    # 计算损失函数。
    y = tf.reshape(y, [-1, 1])
    loss = tf.reduce_sum(tf.multiply(tf.squared_difference(y, predictions),
                         tf.cast(tf.logical_and(tf.less(y, tf.zeros_like(y) - 0.01), tf.greater(predictions, tf.zeros_like(y) + 0.01)), tf.float32) * 2 +
                                     #tf.cast(tf.less(y, predictions), tf.float32) * 1 +
                                     tf.ones_like(y)))
    #loss = tf.losses.mean_squared_error(labels=y, predictions=predictions)

    # 创建模型优化器并得到优化步骤。
    train_op = tf.contrib.layers.optimize_loss(
        loss, tf.train.get_global_step(),
        optimizer="Adam", learning_rate=0.001)
    return predictions, loss, train_op


def run_eval(sess, test_X, test_y, weights, biases):
    # 将测试数据以数据集的方式提供给计算图。
    ds = tf.data.Dataset.from_tensor_slices((test_X, test_y))
    ds = ds.batch(1)
    X, y = ds.make_one_shot_iterator().get_next()

    # 调用模型得到计算结果。这里不需要输入真实的y值。
    with tf.variable_scope("model", reuse=True):
        prediction, _, _ = lstm_model(X, [0.0], False, weights, biases)

    # 将预测结果存入一个数组。
    predictions = []
    labels = []
    for i in range(len(test_X)):
        p, l = sess.run([prediction, y])
        predictions.append(p)
        labels.append(l)

    # 计算rmse作为评价指标。
    predictions = np.array(predictions).squeeze()
    labels = np.array(labels).squeeze()
    rmse = np.sqrt(((predictions - labels) ** 2).mean(axis=0))
    print("Root Mean Square Error is: %f" % rmse)

    # 对预测的sin函数曲线进行绘图。
    plt.figure()
    plt.plot(predictions, label='predictions')
    plt.plot(labels, label='real_close')
    plt.legend()
    plt.show()


# 将训练数据以数据集的方式提供给计算图。
tds = tf.data.Dataset.from_tensor_slices((train_X, train_y))
tds = tds.repeat().shuffle(1000).batch(BATCH_SIZE)
t_X, t_y = tds.make_one_shot_iterator().get_next()


# 定义模型，得到预测结果、损失函数，和训练操作。
with tf.variable_scope("model"):
    _, loss, train_op = lstm_model(t_X, t_y, True, weights, biases)

with tf.Session() as sess:
    sess.run(tf.global_variables_initializer())

    # 测试在训练之前的模型效果。
    # print("Evaluate model before training.")
    # run_eval(sess, test_X, test_y)

    # print(sess.run(x_shape))

    # 训练模型。
    for i in range(TRAINING_STEPS):
        _, l = sess.run([train_op, loss])
        if i % 1000 == 0:
            print("train step: " + str(i) + ", loss: " + str(l))

    # 使用训练好的模型对测试数据进行预测。
    print("Evaluate model after training.")
    run_eval(sess, test_X, test_y, weights, biases)