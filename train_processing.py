import torch
from torch import nn
import datetime
from time import time


class Trainer(object):
    """常规训练过程的框架
    """
    def __init__(self, train_loader, val_loader,
                 model, loss, optimizer, logger=print):
        self.train = train_loader
        self.val = val_loader
        self.model = model
        self.loss = loss
        self.optimizer = optimizer
        self.logger = logger
        # 训练过程相关
        self.current_epoch = 0
        self.current_step = 0
        # 评测相关
        self.best_val_loss = 10000
        self.best_val_acc = 0

    def _log_loss_acc(self, name, loss, acc):
        self.logger(f'{name:6s} | loss:{loss:0.4f} | acc:{acc:0.4f}')

    ##################################
    # cal loss
    #################################
    def set_cal_loss(self, func):
        """设定当前计算loss的函数
        """
        self.cal_loss = func
        self.logger(f'cal_loss: {func.__name__}')

    def cal_loss(self, batch):
        """从 batch 到计算 loss 的函数

        在 train_one_epoch 和 evaluate 中使用
        args：
            batch
        return：
            cur_loss, cur_acc
        """
        return self.cal_mask_loss(batch)

    def cal_mask_loss(self, batch):
        """masked langurage model 用来计算loss的函数

        注意 y_pre.shape = [batch, vocab_len, sentence_len], 指 transpose 之后
        y = [batch, sentence_len]
        y_mask = [batch, sentence_len]
        """
        x, label = batch
        y_pre = self.model(x).transpose(1, 2)  # transpose 是为了匹配后面的loss
        y = self.model.get_token_from_single(label, is_split_into_words=True)['input_ids']
        y_mask = self.model.get_y_mask(y)

        cur_loss = self.loss(y_pre, y)
        # mask 掉不需要预测的
        # 更改了mask text的代码，不会出现nan的情况了,每句话必出现mask字符
        cur_loss = ((cur_loss * y_mask).sum(dim=-1) / y_mask.sum(dim=-1)).mean()
        cur_acc = ((y_pre.argmax(dim=1) == y)*y_mask).sum()/(y_mask.sum()+1e-8)  # 预测对的字符数/mask的字符数
        return cur_loss, cur_acc

    ##################################
    # training
    #################################
    def _train_one_epoch(self):
        self.model.train()  # 开启训练模式
        assert self.model.training

        loss, acc = 0, 0
        for batch in self.train:
            self.current_step += 1
            cur_loss, cur_acc = self.cal_loss(batch)
            # back propagation 三连
            self.optimizer.zero_grad()
            cur_loss.backward()
            self.optimizer.step()

            self._post_processing_per_step()  # 每步之后需要进行的操作
            loss += cur_loss
            acc += cur_acc

        loss /= len(self.train)
        acc /= len(self.train)
        self._log_loss_acc('train', loss, acc)

    def training(self, epoch=10):
        t = datetime.datetime.today()
        self.logger(f'start training: {t}')

        torch.set_grad_enabled(True)
        assert torch.is_grad_enabled()

        t0 = time()
        for e in range(1, epoch + 1):
            self.logger('-' * 42)
            self.current_epoch += 1
            self.logger(f'Epoch: {self.current_epoch}')

            t1 = time()
            self._train_one_epoch()
            t2 = time()
            self.logger(f'cost:{(t2 - t1) / 3600:0.2f}h')

            current_val_loss, current_val_acc = self.evaluate(self.val, 'val')
            if self.best_val_loss > current_val_loss:
                self.best_val_loss = current_val_loss
                self.model.save('best_val_loss')
                print('saved best val loss model')

            if self.best_val_acc < current_val_acc:
                self.best_val_acc = current_val_acc
                self.model.save('best_val_acc')
                print('saved best val acc model')

            self._post_processing_per_epoch()  # 每个epoch之后要做的事情

        t3 = time()
        print(f'total cost: {(t3 - t0) / 3600:0.2f}h')

    ################################
    # evaluate
    ###############################
    def evaluate(self, data_loader, name):
        self.model.eval()  # 开启测试模式
        assert not self.model.training

        loss, acc = 0, 0
        with torch.no_grad():
            for batch in data_loader:
                cur_loss, cur_acc = self.cal_loss(batch)
                loss += cur_loss
                acc += cur_acc
            loss /= len(data_loader)
            acc /= len(data_loader)
            self._log_loss_acc(name, loss, acc)
            return loss, acc

    def _post_processing_per_epoch(self):
        pass

    def _post_processing_per_step(self):
        pass